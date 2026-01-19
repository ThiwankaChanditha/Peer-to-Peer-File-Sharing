from pathlib import Path

def reassemble(chunks, output_file):
    with open(output_file, "wb") as out:
        for chunk in sorted(chunks, key=lambda x: x["index"]):
            with open(Path("storage/chunks") / chunk["filename"], "rb") as cf:
                out.write(cf.read())
