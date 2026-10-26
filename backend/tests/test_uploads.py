"""The ingestion boundary must fail before extraction or paid API calls."""

from io import BytesIO

import pytest
from starlette.datastructures import Headers, UploadFile

from app.errors import InvalidUpload, UploadTooLarge
from app.uploads import read_upload, validate_file_type


def test_type_and_basename():
    assert validate_file_type("../../notes.TXT", "text/plain; charset=utf-8") == (
        "notes.TXT",
        ".txt",
    )


@pytest.mark.parametrize(
    "name,mime",
    [
        ("app.exe", "application/octet-stream"),
        ("notes.pdf", "text/plain"),
        ("notes.txt", None),
        ("bad\nname.txt", "text/plain"),
    ],
)
def test_invalid_types(name, mime):
    with pytest.raises(InvalidUpload):
        validate_file_type(name, mime)


@pytest.mark.parametrize(
    "data,limit,error", [(b"", 10, InvalidUpload), (b"four", 3, UploadTooLarge)]
)
def test_upload_size(data, limit, error):
    file = UploadFile(
        BytesIO(data), filename="a.txt", headers=Headers({"content-type": "text/plain"})
    )
    with pytest.raises(error):
        read_upload(file, limit)
    assert file.file.closed
