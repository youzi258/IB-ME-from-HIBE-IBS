// Finite integer-Gaussian rejection sampling and complete native GPV loops.
// Weights are floor(2^mass_bits exp(-((x-c)^2-d(c,Z)^2)/(2 sigma^2))).
// A bounded symmetric integer window is used.  No normal variates or rounding
// of normal variates are used.  This finite law is not an unbounded Gaussian.
#include <mpfr.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/crypto.h>
#include <omp.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cfloat>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef IBME_SOURCE_SHA256
#define IBME_SOURCE_SHA256 "unbound-build"
#endif

namespace {
using U128 = unsigned __int128;
struct Failure : std::runtime_error { int code; Failure(int c, const char* s):std::runtime_error(s),code(c){} };
constexpr int GRID = 256;
static_assert(LDBL_MANT_DIG >= 64,"outward intervals require at least 64 mantissa bits");
static_assert(sizeof(long)==8,"native MPFR integer conversion requires 64-bit long");
constexpr uint64_t MAX_RADIUS = 1ULL << 40;
constexpr double MAX_CENTER = 0x1p50;
constexpr uint64_t MAX_COUNT = 1ULL << 32;
struct Policy { double tail; int mass, precision, attempts; };

void check_policy(const Policy& p) {
    if (!std::isfinite(p.tail) || p.tail < 6 || p.tail > 32 || p.mass < 32 || p.mass > 192 ||
        p.precision < p.mass + 64 || p.precision > 4096 || p.attempts < 1 || p.attempts > 1000000)
        throw Failure(1,"invalid finite Gaussian policy");
}

// Four fixed limbs cover mass<=192 plus a bounded 42-bit window size.
struct U256 { uint64_t words[4]={0,0,0,0}; };
bool less(const U256&a,const U256&b) {
    for(int i=3;i>=0;--i)if(a.words[i]!=b.words[i])return a.words[i]<b.words[i];
    return false;
}
bool zero(const U256&a){return !(a.words[0]|a.words[1]|a.words[2]|a.words[3]);}
U256 add(U256 a,U256 b) {
    U256 result;uint64_t carry=0;
    for(int i=0;i<4;++i){U128 s=U128(a.words[i])+b.words[i]+carry;result.words[i]=uint64_t(s);carry=uint64_t(s>>64);}
    if(carry)throw Failure(2,"envelope mass overflow");return result;
}
U256 decrement(U256 a) {
    for(int i=0;i<4;++i){if(a.words[i]-- != 0)break;}return a;
}
struct Threshold { U256 value; };
bool below(const U256&x, const Threshold& t) { return less(x,t.value); }
Threshold from_mpfr(mpfr_srcptr x, bool ceil) {
    mpz_t z; mpz_init(z);
    mpfr_get_z(z,x,ceil?MPFR_RNDU:MPFR_RNDD);
    if (mpz_sgn(z)<0) { mpz_clear(z); throw Failure(3,"negative Gaussian mass"); }
    Threshold out;
    if (mpz_sizeinbase(z,2)>256) {mpz_clear(z);throw Failure(2,"Gaussian mass overflow");}
    size_t count=0;mpz_export(out.value.words,&count,-1,sizeof(uint64_t),0,0,z);
    mpz_clear(z); return out;
}

U256 multiply(const Threshold&t,uint64_t count) {
    U256 result;uint64_t carry=0;
    for(int i=0;i<4;++i){U128 s=U128(t.value.words[i])*count+carry;result.words[i]=uint64_t(s);carry=uint64_t(s>>64);}
    if(carry)throw Failure(2,"envelope product overflow");return result;
}
int bits64(uint64_t x) { return x?64-__builtin_clzll(x):0; }

class Stream {
    EVP_CIPHER_CTX* ctx=nullptr;
    unsigned char buffer[4096]; size_t used=sizeof(buffer);
public:
    Stream(const unsigned char master[32],uint64_t domain,uint64_t index) {
        // Domain and index are canonical little-endian and never share streams.
        unsigned char input[64]={0},key[32],iv[16]={0};
        const char label[]="IBME-WANG-PW-DG-v1";
        memcpy(input,label,sizeof(label)-1); memcpy(input+24,master,32);
        for(int i=0;i<8;++i)input[56+i]=uint8_t(index>>(8*i));
        for(int i=0;i<8;++i)iv[8+i]=uint8_t(domain>>(8*i));
        unsigned int len=0;
        if(EVP_Digest(input,sizeof(input),key,&len,EVP_sha256(),nullptr)!=1 || len!=32)
            throw Failure(4,"OpenSSL stream derivation failed");
        ctx=EVP_CIPHER_CTX_new();
        if(!ctx || EVP_EncryptInit_ex(ctx,EVP_chacha20(),nullptr,key,iv)!=1) {
            OPENSSL_cleanse(key,sizeof(key)); if(ctx)EVP_CIPHER_CTX_free(ctx); ctx=nullptr;
            throw Failure(4,"OpenSSL ChaCha20 initialization failed");
        }
        OPENSSL_cleanse(key,sizeof(key)); OPENSSL_cleanse(input,sizeof(input));
    }
    ~Stream(){if(ctx)EVP_CIPHER_CTX_free(ctx);OPENSSL_cleanse(buffer,sizeof(buffer));}
    uint64_t word() {
        if(used+8>sizeof(buffer)) {
            unsigned char zero[sizeof(buffer)]={0}; int len=0;
            if(EVP_EncryptUpdate(ctx,buffer,&len,zero,sizeof(zero))!=1 || len!=sizeof(buffer))
                throw Failure(4,"OpenSSL ChaCha20 generation failed");
            used=0;
        }
        uint64_t v=0;for(int i=0;i<8;++i)v|=uint64_t(buffer[used++])<<(8*i);return v;
    }
    uint64_t uniform64(uint64_t bound) {
        if(!bound)throw Failure(1,"empty uniform range");
        uint64_t cutoff=uint64_t(-bound)%bound;
        for(int i=0;i<4096;++i){uint64_t x=word();if(x>=cutoff)return x%bound;}
        throw Failure(5,"uniform rejection budget exceeded");
    }
    U256 uniform(U256 bound) {
        if(zero(bound))throw Failure(1,"empty uniform mass");
        U256 max=decrement(bound);int bits=0;
        for(int i=3;i>=0;--i)if(max.words[i]){bits=64*i+bits64(max.words[i]);break;}
        int limbs=(bits+63)/64;
        for(int i=0;i<4096;++i){
            U256 x;for(int j=0;j<limbs;++j)x.words[j]=word();
            if(bits%64)x.words[limbs-1]&=(uint64_t(1)<<(bits%64))-1;
            if(less(x,bound))return x;
        }
        throw Failure(5,"envelope rejection budget exceeded");
    }
};

void seed_master(const unsigned char*seed,size_t length,unsigned char out[32]) {
    if(seed){if(length!=32)throw Failure(1,"seed must have 32 bytes");memcpy(out,seed,32);}
    else if(length || RAND_bytes(out,32)!=1)throw Failure(4,"OpenSSL RAND_bytes failed");
}

// Basic long-double interval operations are rounded out by one representable
// value after each IEEE operation.  No libm exp/log result is trusted here.
long double down(long double x){return std::nextafter(x,-std::numeric_limits<long double>::infinity());}
long double up(long double x){return std::nextafter(x,std::numeric_limits<long double>::infinity());}
struct Interval { long double lo,hi; };
Interval sub(Interval a,Interval b){return {down(a.lo-b.hi),up(a.hi-b.lo)};}
Interval square(Interval a) {
    if(a.lo<=0 && a.hi>=0)return {0,up(std::max(a.lo*a.lo,a.hi*a.hi))};
    return {std::max(0.L,down(std::min(a.lo*a.lo,a.hi*a.hi))),up(std::max(a.lo*a.lo,a.hi*a.hi))};
}
Interval energy(int64_t x,double center,double sigma) {
    Interval c{(long double)center,(long double)center};
    Interval delta=sub({(long double)x,(long double)x},c);
    long double nearest=std::round((long double)center);
    Interval small=sub({nearest,nearest},c), s=square({(long double)sigma,(long double)sigma});
    Interval numer=sub(square(delta),square(small));
    return {std::max(0.L,down(numer.lo/up(2*s.hi))),std::max(0.L,up(numer.hi/down(2*s.lo)))};
}

struct ExpTable {
    int mass,precision; std::vector<Threshold> lower,upper;
    ExpTable(const Policy&p):mass(p.mass),precision(p.precision) {
        size_t count=size_t(p.mass)*GRID+2;lower.resize(count);upper.resize(count);
        mpfr_t t,a,b;mpfr_inits2(p.precision,t,a,b,(mpfr_ptr)nullptr);
        for(size_t i=0;i<count;++i){
            mpfr_set_ui(t,i,MPFR_RNDN);mpfr_div_2ui(t,t,8,MPFR_RNDN);mpfr_neg(t,t,MPFR_RNDN);
            mpfr_exp(a,t,MPFR_RNDD);mpfr_exp(b,t,MPFR_RNDU);
            mpfr_mul_2ui(a,a,p.mass,MPFR_RNDD);mpfr_mul_2ui(b,b,p.mass,MPFR_RNDU);
            lower[i]=from_mpfr(a,false);upper[i]=from_mpfr(b,true);
        }
        mpfr_clears(t,a,b,(mpfr_ptr)nullptr);
    }
};
std::mutex table_lock;
std::vector<std::shared_ptr<ExpTable>> table_cache;
std::shared_ptr<ExpTable> table_for(const Policy&p) {
    std::lock_guard<std::mutex> lock(table_lock);
    for(auto&t:table_cache)if(t->mass==p.mass && t->precision==p.precision)return t;
    if(table_cache.size()>=8)throw Failure(2,"finite Gaussian policy cache limit exceeded");
    auto t=std::make_shared<ExpTable>(p);table_cache.push_back(t);return t;
}

class Precise {
    mpfr_t d0,d1,z0,z1,s0,s1,n0,n1,a,b,c,tmp;
    int precision;
public:
    explicit Precise(int bits):precision(bits){mpfr_inits2(bits,d0,d1,z0,z1,s0,s1,n0,n1,a,b,c,tmp,(mpfr_ptr)nullptr);}
    ~Precise(){mpfr_clears(d0,d1,z0,z1,s0,s1,n0,n1,a,b,c,tmp,(mpfr_ptr)nullptr);}
    void squares(mpfr_ptr lo,mpfr_ptr hi,int64_t x,double center) {
        mpfr_set_si(a,(long)x,MPFR_RNDN);mpfr_set_d(c,center,MPFR_RNDN);
        mpfr_sub(lo,a,c,MPFR_RNDD);mpfr_sub(hi,a,c,MPFR_RNDU);
        if(mpfr_sgn(lo)<=0 && mpfr_sgn(hi)>=0){
            mpfr_sqr(a,lo,MPFR_RNDU);mpfr_sqr(b,hi,MPFR_RNDU);mpfr_max(hi,a,b,MPFR_RNDU);mpfr_set_zero(lo,1);
        } else if(mpfr_sgn(hi)<0){
            mpfr_sqr(a,lo,MPFR_RNDU);mpfr_sqr(lo,hi,MPFR_RNDD);mpfr_set(hi,a,MPFR_RNDU);
        }else{mpfr_sqr(lo,lo,MPFR_RNDD);mpfr_sqr(hi,hi,MPFR_RNDU);}
    }
    bool accept(const U256&u,int64_t x,double center,double sigma,int mass) {
        squares(d0,d1,x,center);
        squares(z0,z1,(int64_t)std::round(center),center);
        mpfr_set_d(a,sigma,MPFR_RNDN);mpfr_sqr(s0,a,MPFR_RNDD);mpfr_sqr(s1,a,MPFR_RNDU);
        mpfr_mul_2ui(s0,s0,1,MPFR_RNDD);mpfr_mul_2ui(s1,s1,1,MPFR_RNDU);
        mpfr_sub(n0,d0,z1,MPFR_RNDD);mpfr_sub(n1,d1,z0,MPFR_RNDU);
        if(mpfr_sgn(n0)<0)mpfr_set_zero(n0,1);if(mpfr_sgn(n1)<0)mpfr_set_zero(n1,1);
        mpfr_div(n0,n0,s1,MPFR_RNDD);mpfr_div(n1,n1,s0,MPFR_RNDU);
        mpfr_neg(a,n1,MPFR_RNDN);mpfr_neg(b,n0,MPFR_RNDN);
        mpfr_exp(a,a,MPFR_RNDD);mpfr_exp(b,b,MPFR_RNDU);
        mpfr_mul_2ui(a,a,mass,MPFR_RNDD);mpfr_mul_2ui(b,b,mass,MPFR_RNDU);
        Threshold lo=from_mpfr(a,false),hi=from_mpfr(b,false);
        if(below(u,lo))return true;if(!below(u,hi))return false;
        // Explicit failure, rather than an arbitrary rounded decision.
        throw Failure(3,"MPFR acceptance decision unresolved at precision budget");
    }
};

struct Shell {uint64_t lo,hi,count;Threshold envelope;U256 cumulative;};
struct Proposal {
    double sigma; uint64_t radius;std::vector<Shell> shells;U256 total;
    Proposal(double value,const Policy&p,const ExpTable&t):sigma(value) {
        if(!std::isfinite(value)||value<=0 || value>double(MAX_RADIUS)/p.tail)
            throw Failure(1,"Gaussian sigma outside fixed resource range");
        radius=(uint64_t)std::ceil(p.tail*value)+1;
        uint64_t step=std::max(uint64_t(1),(uint64_t)std::ceil(value));
        for(uint64_t lo=0;lo<=radius;){
            uint64_t hi=std::min(radius,lo+step-1),count=lo?2*(hi-lo+1):2*hi+1;
            long double dist=lo?lo-1:0;
            long double numer=std::max(0.L,down(down(dist*dist)-0.25L));
            long double den=up(2*up((long double)value*value));
            long double e=std::max(0.L,down(numer/den));
            size_t idx=e>=p.mass?t.upper.size()-1:(size_t)std::floor(std::max(0.L,down(e*GRID)));
            Threshold envelope=t.upper[idx];
            // exp(-mass) < 2^-mass; cells beyond the table have zero target mass.
            if(e>p.mass)envelope=Threshold{};
            total=add(total,multiply(envelope,count));shells.push_back({lo,hi,count,envelope,total});
            lo=hi+1;
        }
    }
};

int64_t draw(double center,const Proposal&p,const Policy&policy,const ExpTable&t,Precise&precise,Stream&rng) {
    if(!std::isfinite(center)||std::abs(center)>MAX_CENTER)throw Failure(1,"Gaussian center outside fixed resource range");
    int64_t base=(int64_t)std::floor(center);
    for(int attempt=0;attempt<policy.attempts;++attempt){
        U256 pick=rng.uniform(p.total);const Shell*shell=nullptr;
        for(const auto&s:p.shells)if(less(pick,s.cumulative)){shell=&s;break;}
        if(!shell)throw Failure(3,"invalid Gaussian envelope selection");
        uint64_t offset=rng.uniform64(shell->count);int64_t displacement;
        if(!shell->lo)displacement=(int64_t)offset-(int64_t)shell->hi;
        else{uint64_t len=shell->hi-shell->lo+1;displacement=offset<len?(int64_t)(shell->lo+offset):-(int64_t)(shell->lo+offset-len);}
        int64_t x=base+displacement;U256 u=rng.uniform(shell->envelope.value);
        if(x==(int64_t)std::round(center))return x;
        Interval e=energy(x,center,p.sigma);
        if(e.lo>=policy.mass)continue;
        size_t low=(size_t)std::floor(std::max(0.L,down(e.lo*GRID)));
        size_t high=e.hi>=policy.mass?t.lower.size():(size_t)std::ceil(std::max(0.L,up(e.hi*GRID)));
        if(high<t.lower.size() && below(u,t.lower[high]))return x;
        if(low>=t.upper.size())continue;
        if(!below(u,t.upper[low]))continue;
        if(precise.accept(u,x,center,p.sigma,policy.mass))return x;
    }
    throw Failure(5,"integer Gaussian rejection budget exceeded");
}

void write_error(char*buffer,size_t size,const char*message){if(buffer&&size){std::strncpy(buffer,message,size-1);buffer[size-1]=0;}}
template<class F>int guarded(char*error,size_t size,F f){try{f();return 0;}catch(const Failure&e){write_error(error,size,e.what());return e.code;}catch(const std::exception&e){write_error(error,size,e.what());return 6;}catch(...){write_error(error,size,"native sampler failure");return 6;}}
}

extern "C" {
int ibme_dg_version(){return 1;}
const char* ibme_dg_source_sha256(){return IBME_SOURCE_SHA256;}

int ibme_draw_gaussian(int64_t*out,uint64_t count,const double*centers,const double*sigmas,int varying,
                      double tail,int mass,int precision,int attempts,const unsigned char*seed,size_t seed_length,
                      int threads,char*error,size_t error_size) {
    return guarded(error,error_size,[&]{
        Policy p{tail,mass,precision,attempts};check_policy(p);
        if(!out||!centers||!sigmas||count>MAX_COUNT||threads<1||threads>256)throw Failure(1,"invalid Gaussian buffers/count/threads");
        auto table=table_for(p);unsigned char master[32];seed_master(seed,seed_length,master);
        std::atomic<int> failure{0};std::string message;std::mutex error_lock;
        std::shared_ptr<Proposal> common;if(!varying)common=std::make_shared<Proposal>(sigmas[0],p,*table);
#pragma omp parallel num_threads(threads)
        {
            std::unique_ptr<Stream>rng;std::unique_ptr<Precise>precise;
            try{rng=std::make_unique<Stream>(master,1,(uint64_t)omp_get_thread_num());precise=std::make_unique<Precise>(precision);}
            catch(const std::exception&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(6))message=e.what();}
#pragma omp for schedule(static)
            for(uint64_t i=0;i<count;++i){
                if(failure.load())continue;
                try{if(varying){Proposal proposal(sigmas[i],p,*table);out[i]=draw(centers[i],proposal,p,*table,*precise,*rng);}
                    else out[i]=draw(centers[0],*common,p,*table,*precise,*rng);}
                catch(const Failure&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(e.code))message=e.what();}
                catch(const std::exception&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(6))message=e.what();}
            }
        }
        OPENSSL_cleanse(master,sizeof(master));if(failure.load())throw Failure(failure.load(),message.c_str());
    });
}

int ibme_sample_gpv(const int64_t*B,const double*star,const double*norms,const int64_t*P,int64_t*out,
                    uint64_t m,uint64_t columns,double sigma,double tail,int mass,int precision,int attempts,
                    const unsigned char*seed,size_t seed_length,int threads,char*error,size_t error_size) {
    return guarded(error,error_size,[&]{
        Policy p{tail,mass,precision,attempts};check_policy(p);
        if(!B||!star||!norms||!P||!out||!m||m>131072||!columns||columns>131072||threads<1||threads>256||
           !std::isfinite(sigma)||sigma<=0 || m>std::numeric_limits<size_t>::max()/m)
            throw Failure(1,"invalid GPV buffers/dimensions/width/threads");
        auto table=table_for(p);std::vector<Proposal>proposals;proposals.reserve(m);
        for(uint64_t i=0;i<m;++i){
            if(!std::isfinite(norms[i])||norms[i]<=0)throw Failure(1,"GPV norm must be finite and positive");
            proposals.emplace_back(sigma/std::sqrt(norms[i]),p,*table);
        }
        for(uint64_t i=0;i<m*m;++i)if(!std::isfinite(star[i]))throw Failure(1,"nonfinite GPV Gram-Schmidt data");
        unsigned char master[32];seed_master(seed,seed_length,master);
        std::atomic<int>failure{0};std::string message;std::mutex error_lock;
#pragma omp parallel num_threads(threads)
        {
            std::vector<double>center;std::unique_ptr<Precise>precise;
            try{center.resize(m);precise=std::make_unique<Precise>(precision);}
            catch(const std::exception&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(6))message=e.what();}
#pragma omp for schedule(dynamic,1)
            for(uint64_t col=0;col<columns;++col){
                if(failure.load())continue;
                try{
                    Stream rng(master,2,col);const int64_t*part=P+col*m;int64_t*target=out+col*m;
                    for(uint64_t j=0;j<m;++j){center[j]=-double(part[j]);target[j]=part[j];}
                    for(uint64_t reverse=0;reverse<m;++reverse){
                        uint64_t i=m-1-reverse;const double*s=star+i*m;const int64_t*b=B+i*m;
                        long double dot=0;for(uint64_t j=0;j<m;++j)dot+=(long double)s[j]*center[j];
                        double ci=double(dot/(long double)norms[i]);
                        int64_t zi=draw(ci,proposals[i],p,*table,*precise,rng);
                        for(uint64_t j=0;j<m;++j){
                            __int128 value=(__int128)target[j]+(__int128)zi*b[j];
                            if(value<std::numeric_limits<int64_t>::min()||value>std::numeric_limits<int64_t>::max())
                                throw Failure(2,"GPV signed integer overflow");
                            target[j]=(int64_t)value;center[j]-=double(zi)*double(b[j]);
                            if(!std::isfinite(center[j]))throw Failure(2,"GPV center overflow");
                        }
                    }
                }catch(const Failure&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(e.code))message=e.what();}
                catch(const std::exception&e){std::lock_guard<std::mutex>l(error_lock);if(!failure.exchange(6))message=e.what();}
            }
        }
        OPENSSL_cleanse(master,sizeof(master));if(failure.load())throw Failure(failure.load(),message.c_str());
    });
}
}
