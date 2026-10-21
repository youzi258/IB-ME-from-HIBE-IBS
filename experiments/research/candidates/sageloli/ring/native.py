"""Explicit local native build and exact arithmetic handles (WSL Sage prefix)."""
import argparse
import ctypes as C
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE=Path(__file__).resolve().parent


def source_id():
    return sha256((HERE/"native.cpp").read_bytes()+b"-O3 -fopenmp -lflint -lgmp v1").hexdigest()


def build(directory, *, dependency_mode=None):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    if os.name!="posix": raise RuntimeError("native build requires a POSIX host")
    mode=dependency_mode or os.environ.get("IBME_NATIVE_DEPENDENCY_MODE","sage-prefix")
    if mode not in ("sage-prefix","host-toolchain"):
        raise RuntimeError("choose sage-prefix or host-toolchain native dependencies")
    prefix=Path.home()/"miniconda3/envs/sage"
    if mode=="sage-prefix" and not (prefix/"include/flint/fmpz_poly.h").is_file():
        raise RuntimeError("configured Sage prefix lacks FLINT development headers")
    cxx=os.environ.get("CXX","g++")
    if not cxx or any(character.isspace() for character in cxx):
        raise RuntimeError("CXX must name one compiler executable without arguments")
    target=directory/("sageloli-ring-"+source_id()+".so")
    if target.exists(): return target
    with tempfile.TemporaryDirectory(prefix="build-",dir=directory) as tmp:
        out=Path(tmp)/"ring.so"
        cmd=[cxx,"-O3","-std=c++17","-fPIC","-shared","-fopenmp",
             '-DSG_SOURCE_ID="'+source_id()+'"']
        if mode=="sage-prefix": cmd.extend(["-I"+str(prefix/"include")])
        cmd.append(str(HERE/"native.cpp"))
        if mode=="sage-prefix": cmd.extend(["-L"+str(prefix/"lib"),"-Wl,-rpath,"+str(prefix/"lib")])
        cmd.extend(["-lflint","-lgmp","-o",str(out)])
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        if result.returncode: raise RuntimeError("native build failed: "+result.stderr[-4000:])
        out.replace(target)
    return target


class Library:
    def __init__(self,path=None):
        path=path or os.environ.get("IBME_SAGELOLI_RING_NATIVE")
        if not path: raise RuntimeError("set explicit IBME_SAGELOLI_RING_NATIVE path after native build")
        self.path=Path(path).resolve(); self.lib=C.CDLL(str(self.path))
        self.lib.sg_source_id.restype=C.c_char_p
        if self.lib.sg_source_id().decode()!=source_id(): raise ValueError("native source version mismatch")
        p=C.c_void_p;i=C.c_int
        for name,args,result in (("sg_small_new",[p,i,i,i],p),("sg_small_free",[p],None),
                ("sg_small_apply",[p,p,p],i),("sg_wide_new",[p,i,i,i],p),
                ("sg_wide_free",[p],None),("sg_wide_apply",[p,p,p,i,p],i)):
            fn=getattr(self.lib,name);fn.argtypes=args;fn.restype=result

    def metadata(self):
        return dict(source_id=source_id(),binary_sha256=sha256(self.path.read_bytes()).hexdigest(),
                    exact_arithmetic="two-prime range-checked NTT + FLINT integer polynomial products")


def _i64(values,shape):
    import numpy as np
    a=np.asarray(values)
    if a.shape!=tuple(shape) or a.dtype.kind not in "iu" or a.dtype.itemsize>8:
        raise ValueError("exact int64 tensor required")
    if a.dtype.kind=="u" and a.size and a.max()>2**63-1: raise ValueError("int64 overflow")
    return np.ascontiguousarray(a,dtype=np.int64)


class SmallMatrix:
    def __init__(self,library,values):
        import numpy as np
        a=np.asarray(values)
        if a.ndim!=3: raise ValueError("polynomial matrix required")
        self.shape=a.shape;self.library=library
        a=_i64(a,a.shape)
        self.handle=library.lib.sg_small_new(a.ctypes.data,*a.shape)
        if not self.handle: raise ValueError("native small matrix admission failed")

    def apply(self,values):
        import numpy as np
        if not self.handle: raise ValueError("closed arithmetic handle")
        r,c,d=self.shape;a=_i64(values,(c,d));out=np.empty((r,d),dtype=np.int64)
        if self.library.lib.sg_small_apply(self.handle,a.ctypes.data,out.ctypes.data):
            raise ValueError("exact NTT product range or arithmetic failure")
        return out

    def close(self):
        if getattr(self,"handle",None):
            self.library.lib.sg_small_free(self.handle);self.handle=None

    def __del__(self): self.close()


class WideRow:
    def __init__(self,library,values,q):
        import numpy as np
        a=np.asarray(values,dtype=object)
        if a.ndim!=2 or type(q) is not int or not 2<=q<2**512: raise ValueError("wide ring row required")
        self.cols,self.d=a.shape;self.q=q;self.width=(q.bit_length()+7)//8;self.library=library
        if any(type(v) is not int or not 0<=v<q for v in a.flat): raise ValueError("noncanonical public coefficient")
        raw=b"".join(v.to_bytes(self.width,"big") for v in a.flat)
        self.handle=library.lib.sg_wide_new(raw,self.width,self.cols,self.d)
        if not self.handle: raise ValueError("native wide matrix admission failed")

    def apply(self,values):
        import numpy as np
        if not self.handle: raise ValueError("closed arithmetic handle")
        a=_i64(values,(self.cols,self.d));out=C.create_string_buffer(self.d*self.width)
        if self.library.lib.sg_wide_apply(self.handle,a.ctypes.data,self.q.to_bytes(self.width,"big"),self.width,out):
            raise ValueError("exact wide polynomial operation failed")
        return np.array([int.from_bytes(out.raw[i*self.width:(i+1)*self.width],"big")
                         for i in range(self.d)],dtype=object)

    def close(self):
        if getattr(self,"handle",None):
            self.library.lib.sg_wide_free(self.handle);self.handle=None

    def __del__(self): self.close()


def main():
    p=argparse.ArgumentParser();p.add_argument("--directory",type=Path,required=True)
    a=p.parse_args();path=build(a.directory);lib=Library(path)
    print(json.dumps(dict(path=str(path),**lib.metadata())))


if __name__=="__main__": main()
