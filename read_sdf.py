import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

# CHANCES SDF wrapper before the CASPEX camera frame header
CHANCES_HEADER_BYTES = 25

# CASPEX camera frame header, Table 25 of the camera manual
CASPEX_HEADER_BYTES = 36

# First byte of packed image data
PIXEL_DATA_OFFSET = (
    CHANCES_HEADER_BYTES + CASPEX_HEADER_BYTES
)

# Detected automatically from the camera header
WIDTH = None
HEIGHT = None
BITS_PER_PIXEL = None

N_PIXELS = None
IMAGE_BYTES = None


# ============================================================
# SDF files
# ============================================================

# Earlier images
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-10:48:45/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:18:47/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:22:20/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:26:24/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:30:31/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:34:19/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:41:25/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:48:35/Image_0x0_0x20000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-11:56:41/Image_0x0_0x40000000.sdf'

# Grid images
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-13:24:46/Image_0x0_0x40000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-13:52:57/Image_0x0_0x40000000.sdf'

# Recent images
#filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:00:45/Image_0x0_0x40000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:19:28/Image_0x0_0x40000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:25:24/Image_0x0_0x40000000.sdf'
#
filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:31:33/Image_0x0_0x40000000.sdf'

# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:38:13/Image_0x0_0x40000000.sdf'
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:45:46/Image_0x0_0x40000000.sdf'
filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-11-06-17:53:24/Image_0x0_0x40000000.sdf'

# ============================================================
# Read SDF and camera header
# ============================================================

def read_sdf(filename):

    global WIDTH
    global HEIGHT
    global BITS_PER_PIXEL
    global N_PIXELS
    global IMAGE_BYTES

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"SDF file not found:\n{path}"
        )

    raw = path.read_bytes()

    if len(raw) < PIXEL_DATA_OFFSET:
        raise ValueError(
            "File is too small to contain the CASPEX header."
        )

    # --------------------------------------------------------
    # Extract CASPEX frame header
    # --------------------------------------------------------

    header = raw[
        CHANCES_HEADER_BYTES:
        PIXEL_DATA_OFFSET
    ]

    # CASPEX Table 25 uses 1-based byte numbering.
    #
    # Bytes 1-4:  Frame length
    # Byte 5:     Data format
    # Bytes 22-23: Frame width
    # Bytes 24-25: Frame height

    frame_length = int.from_bytes(
        header[0:4],
        byteorder="little"
    )

    data_format = header[4] & 0x03

    WIDTH = int.from_bytes(
        header[21:23],
        byteorder="little"
    ) & 0x1FFF

    HEIGHT = int.from_bytes(
        header[23:25],
        byteorder="little"
    ) & 0x0FFF

    # CASPEX Table 26:
    # 1 = 12-bit
    # 2 = 8-bit
    # 3 = 24-bit

    format_to_bits = {
        1: 12,
        2: 8,
        3: 24
    }

    if data_format not in format_to_bits:
        raise ValueError(
            f"Unsupported CASPEX data format: {data_format}"
        )

    BITS_PER_PIXEL = format_to_bits[data_format]

    if WIDTH <= 0 or HEIGHT <= 0:
        raise ValueError(
            f"Invalid image dimensions: {WIDTH} x {HEIGHT}"
        )

    N_PIXELS = WIDTH * HEIGHT

    IMAGE_BYTES = (
        N_PIXELS * BITS_PER_PIXEL + 7
    ) // 8

    # --------------------------------------------------------
    # Check image length
    # --------------------------------------------------------

    available_bytes = (
        len(raw) - PIXEL_DATA_OFFSET
    )

    missing_bytes = (
        IMAGE_BYTES - available_bytes
    )

    print()
    print("=" * 70)
    print("FILE")
    print("=" * 70)

    print(f"File:                  {path.name}")
    print(f"File size:             {len(raw):,} bytes")

    print()
    print("=" * 70)
    print("CASPEX FRAME HEADER")
    print("=" * 70)

    print(f"Frame length:          {frame_length:,} bytes")
    print(f"Data format:           {data_format}")
    print(f"Width:                 {WIDTH} pixels")
    print(f"Height:                {HEIGHT} pixels")
    print(f"Bits per pixel:        {BITS_PER_PIXEL}")

    print()
    print("=" * 70)
    print("IMAGE DATA")
    print("=" * 70)

    print(f"Pixel data offset:     {PIXEL_DATA_OFFSET} bytes")
    print(f"Expected image bytes:  {IMAGE_BYTES:,}")
    print(f"Available image bytes: {available_bytes:,}")
    print(f"Missing image bytes:   {max(0, missing_bytes):,}")

    # The frame-length field should describe the camera
    # header plus its image payload.

    expected_frame_length = (
        CASPEX_HEADER_BYTES + IMAGE_BYTES
    )

    if frame_length != expected_frame_length:
        raise ValueError(
            "CASPEX frame length does not match "
            "the dimensions and pixel format.\n"
            f"Header declares: {frame_length:,} bytes\n"
            f"Expected:        {expected_frame_length:,} bytes"
        )

    if missing_bytes > 1:
        raise ValueError(
            f"Image is missing {missing_bytes:,} bytes. "
            "Refusing to decode a potentially incomplete image."
        )

    if missing_bytes == 1:
        print()
        print(
            "WARNING: The image is missing its final byte."
        )
        print(
            "The affected final pixel will be marked invalid."
        )

    if missing_bytes < 0:
        print()
        print(
            f"NOTE: {abs(missing_bytes)} trailing byte(s) "
            "exist after the expected image data."
        )

    return raw


# ============================================================
# CASPEX 12-bit decoder
# ============================================================

def decode_12bit(data):
    """
    Decode the packed 12-bit format specified in
    CASPEX Table 26.

    Three bytes encode two pixels.

    An incomplete final group is handled explicitly.
    """

    if BITS_PER_PIXEL != 12:
        raise ValueError(
            f"This decoder supports 12-bit data, "
            f"but the header specifies {BITS_PER_PIXEL} bits."
        )

    if len(data) > IMAGE_BYTES:
        data = data[:IMAGE_BYTES]

    missing = IMAGE_BYTES - len(data)

    if missing < 0 or missing > 1:
        raise ValueError(
            f"Unexpected image-data length: {len(data):,}"
        )

    # Pad one missing final byte only to allow decoding.
    # The pixel affected by the missing byte is then
    # explicitly marked NaN.

    if missing == 1:
        data = data + b"\x00"

    groups = np.frombuffer(
        data,
        dtype=np.uint8
    ).reshape(-1, 3)

    b0 = groups[:, 0].astype(np.uint16)
    b1 = groups[:, 1].astype(np.uint16)
    b2 = groups[:, 2].astype(np.uint16)

    p0 = (
        b0
        | ((b1 & 0x0F) << 8)
    )

    p1 = (
        (b2 << 4)
        | (b1 >> 4)
    )

    pixels = np.empty(
        N_PIXELS,
        dtype=np.uint16
    )

    pixels[0::2] = p0
    pixels[1::2] = p1

    image = pixels.reshape(
        HEIGHT,
        WIDTH
    )

    if missing == 1:
        image = image.astype(np.float32)
        image[-1, -1] = np.nan

    return image


# ============================================================
# Print image statistics
# ============================================================

def print_image_statistics(image):

    valid = image[np.isfinite(image)]

    if valid.size == 0:
        raise ValueError(
            "Image contains no valid pixels."
        )

    mean = np.mean(valid)
    median = np.median(valid)
    std = np.std(valid)

    minimum = np.min(valid)
    maximum = np.max(valid)

    saturated = (
        100.0 * np.mean(valid == 4095)
    )

    invalid = np.count_nonzero(
        ~np.isfinite(image)
    )

    print()
    print("=" * 70)
    print("IMAGE")
    print("=" * 70)

    print("Shape:       ", image.shape)
    print("Minimum:     ", minimum)
    print("Maximum:     ", maximum)
    print("Mean:        ", mean)
    print("Median:      ", median)
    print("Std:         ", std)
    print("Saturated:   ", f"{saturated:.4f} %")
    print("Invalid:     ", invalid)

    return mean, median, std, saturated


# ============================================================
# Plot image + histogram
# ============================================================

def plot_image(
    image,
    filename,
    offset,
    mean,
    median,
    std,
    saturated
):

    valid = image[np.isfinite(image)]

    vmin, vmax = np.percentile(
        valid,
        [1, 99]
    )

    print()
    print(
        f"Display range: "
        f"{vmin:.0f} -> {vmax:.0f} DN"
    )

    fig, (ax_img, ax_hist) = plt.subplots(
        1,
        2,
        figsize=(16, 7),
        gridspec_kw={
            "width_ratios": [1.2, 1]
        }
    )

    # --------------------------------------------------------
    # Image
    # --------------------------------------------------------

    im = ax_img.imshow(
        image,
        cmap="gray",
        vmin=vmin,
        vmax=vmax,
        origin="upper",
        interpolation="nearest",
        aspect="equal"
    )

    fig.colorbar(
        im,
        ax=ax_img,
        label="12-bit DN"
    )

    ax_img.set_title(
        f"CHANCES SDF\n"
        f"{WIDTH} x {HEIGHT}, "
        f"{BITS_PER_PIXEL}-bit, "
        f"offset {offset}"
    )

    ax_img.set_xlabel("X pixel")
    ax_img.set_ylabel("Y pixel")

    # --------------------------------------------------------
    # Histogram
    # --------------------------------------------------------

    ax_hist.hist(
        valid,
        bins=256,
        range=(0, 4096)
    )

    ax_hist.axvline(
        median,
        linestyle="--",
        label=f"Median = {median:.1f}"
    )

    ax_hist.axvline(
        mean,
        linestyle=":",
        label=f"Mean = {mean:.1f}"
    )

    ax_hist.set_xlim(0, 4096)

    ax_hist.set_xlabel("12-bit DN")
    ax_hist.set_ylabel("Number of pixels")
    ax_hist.set_title("Pixel histogram")
    ax_hist.legend()

    # --------------------------------------------------------
    # Statistics box
    # --------------------------------------------------------

    stats = (
        f"Dimensions: {WIDTH} x {HEIGHT}\n"
        f"Bit depth: {BITS_PER_PIXEL}\n"
        f"Offset: {offset} bytes\n"
        f"Min: {np.min(valid):.0f}\n"
        f"Max: {np.max(valid):.0f}\n"
        f"Mean: {mean:.1f}\n"
        f"Median: {median:.1f}\n"
        f"Std: {std:.1f}\n"
        f"Saturated: {saturated:.3f}%"
    )

    ax_hist.text(
        0.98,
        0.97,
        stats,
        transform=ax_hist.transAxes,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(
            boxstyle="round",
            alpha=0.8
        )
    )

    plt.tight_layout()

    output = (
        str(Path(filename).with_suffix(""))
        + "_analysis.png"
    )

    plt.savefig(
        output,
        dpi=150
    )

    print()
    print("Saved:", output)

    plt.show()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Read SDF and detect image configuration
    # --------------------------------------------------------

    raw = read_sdf(filename)

    # --------------------------------------------------------
    # Extract packed image data
    # --------------------------------------------------------

    data = raw[
        PIXEL_DATA_OFFSET:
        PIXEL_DATA_OFFSET + IMAGE_BYTES
    ]

    # --------------------------------------------------------
    # Decode image
    # --------------------------------------------------------

    image = decode_12bit(data)

    # --------------------------------------------------------
    # Image statistics
    # --------------------------------------------------------

    mean, median, std, saturated = (
        print_image_statistics(image)
    )

    # --------------------------------------------------------
    # Plot image
    # --------------------------------------------------------

    plot_image(
        image=image,
        filename=filename,
        offset=PIXEL_DATA_OFFSET,
        mean=mean,
        median=median,
        std=std,
        saturated=saturated
    )