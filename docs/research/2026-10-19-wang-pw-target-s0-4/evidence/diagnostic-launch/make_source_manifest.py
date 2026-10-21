import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

directory = Path(__file__).resolve().parent
archive = directory / 'source-ed10d6f.tar'
files = {}
with tarfile.open(archive, 'r:') as stream:
    for member in stream:
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts
        assert not member.issym() and not member.islnk()
        if member.isdir():
            continue
        assert member.isfile() and member.name not in files
        data = stream.extractfile(member).read()
        files[member.name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
result = dict(schema='IBME/WANG-PW-DIAGNOSTIC-SOURCE/1',
              source_commit='ed10d6f126fb5deb89692164d749b95d5512b0a6',
              archive_bytes=archive.stat().st_size,
              archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
              regular_file_count=len(files), files=files)
(directory/'source-manifest.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({key: value for key, value in result.items() if key!='files'},sort_keys=True))
