import base64
import io
from PIL import Image

from service.FileService import normalize_image_for_llm


def test_normalize_webp_image():
    # Create a small WEBP image
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    webp_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(webp_b64, "image/webp")

    assert norm_mime in ("image/jpeg", "image/png")
    out_img = Image.open(io.BytesIO(base64.b64decode(norm_b64)))
    assert out_img.format in ("JPEG", "PNG")
    assert out_img.size == (100, 100)


def test_normalize_transparent_webp_image():
    # Create a transparent WEBP image
    img = Image.new("RGBA", (50, 50), color=(0, 255, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    webp_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(webp_b64, "image/webp")

    assert norm_mime == "image/png"
    out_img = Image.open(io.BytesIO(base64.b64decode(norm_b64)))
    assert out_img.format == "PNG"


def test_normalize_oversized_image():
    # Create an image larger than MAX_IMAGE_DIMENSION (2048)
    img = Image.new("RGB", (3000, 1500), color=(0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    large_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(large_b64, "image/jpeg")

    assert norm_mime == "image/jpeg"
    out_img = Image.open(io.BytesIO(base64.b64decode(norm_b64)))
    assert max(out_img.size) == 2048


def test_normalize_passthrough_clean_jpeg():
    # Standard clean JPEG within limits
    img = Image.new("RGB", (200, 200), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(jpg_b64, "image/jpeg")

    assert norm_mime == "image/jpeg"
    assert norm_b64 == jpg_b64


def test_normalize_handles_data_uri_prefix():
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{jpg_b64}"

    norm_b64, norm_mime = normalize_image_for_llm(data_uri, "image/jpeg")

    assert norm_mime == "image/jpeg"
    assert norm_b64 == jpg_b64


def test_normalize_cmyk_jpeg():
    # CMYK JPEG (common from Photoshop / print)
    img = Image.new("CMYK", (60, 60), color=(50, 100, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    cmyk_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(cmyk_b64, "image/jpeg")

    assert norm_mime == "image/jpeg"
    out_img = Image.open(io.BytesIO(base64.b64decode(norm_b64)))
    assert out_img.mode == "RGB"
    assert out_img.format == "JPEG"


def test_normalize_fake_extension_webp_as_jpeg():
    # File actually containing WEBP bytes but claimed to be image/jpeg
    img = Image.new("RGB", (80, 80), color=(10, 200, 50))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    webp_bytes_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    norm_b64, norm_mime = normalize_image_for_llm(webp_bytes_b64, "image/jpeg")

    out_img = Image.open(io.BytesIO(base64.b64decode(norm_b64)))
    assert out_img.format in ("JPEG", "PNG")
    assert out_img.mode == "RGB"
