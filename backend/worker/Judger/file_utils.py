import io
import tarfile
import time

def extract_file_from_container(container, file_path):
    """
    Extracts a single file from the container's path as a string.
    Reads the tar archive stream returned by get_archive.
    """
    try:
        stream, _ = container.get_archive(file_path)
        file_obj = io.BytesIO()
        for chunk in stream:
            file_obj.write(chunk)
        file_obj.seek(0)
        
        with tarfile.open(fileobj=file_obj, mode='r') as tar:
            member = tar.next() # There should be exactly one file
            f = tar.extractfile(member)
            return f.read().decode('utf-8')
    except Exception as e:
        print(f" [*] Failed to extract {file_path} from container: {e}")
        return ""


def put_files_to_container(container, language, src_code, std_in, expected_out=None):
    """
    Packs the source code, standard input, and expected output into an in-memory 
    tar archive and streams it directly into the container's /workspace directory.
    """
    # Define filenames
    SRC_FILES = {"cpp": "main.cpp", "py": "main.py", "java": "Main.java"}
    
    # Create an in-memory byte stream for the tar file
    tar_stream = io.BytesIO()
    
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        # Add Source Code
        if src_code:
            src_bytes = src_code.encode('utf-8')
            tarinfo = tarfile.TarInfo(name=SRC_FILES.get(language, "main.txt"))
            tarinfo.size = len(src_bytes)
            tarinfo.mtime = time.time()
            tar.addfile(tarinfo, io.BytesIO(src_bytes))
            
        # Add Standard Input
        if std_in is not None:
            in_bytes = std_in.encode('utf-8')
            tarinfo = tarfile.TarInfo(name="input.txt")
            tarinfo.size = len(in_bytes)
            tarinfo.mtime = time.time()
            tar.addfile(tarinfo, io.BytesIO(in_bytes))
            
        # Add Expected Output
        if expected_out is not None:
            out_bytes = expected_out.encode('utf-8')
            tarinfo = tarfile.TarInfo(name="expected_op.txt")
            tarinfo.size = len(out_bytes)
            tarinfo.mtime = time.time()
            tar.addfile(tarinfo, io.BytesIO(out_bytes))
            
    # Reset stream pointer to beginning
    tar_stream.seek(0)
    
    # Stream the tar archive into the container's /workspace
    container.put_archive("/workspace", tar_stream)
