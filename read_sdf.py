import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

WIDTH = 1280
HEIGHT = 1028
BITS_PER_PIXEL = 12

N_PIXELS = WIDTH * HEIGHT
IMAGE_BYTES = N_PIXELS * BITS_PER_PIXEL // 8


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
filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-15-13:52:57/Image_0x0_0x40000000.sdf'

# Current image
# filename = '/Volumes/Space/Projects/CHANCES/03_Engineering/04_Optical engineering/EM_images/2026-10-16-12:10:20/Image_0x0_0x40000000.sdf'


# ============================================================
# Read SDF
# ============================================================

def read_sdf(filename):
    """
    Read the complete downloaded SDF file.

    SaveImgsToFile() has already removed the PUS service-168
    telemetry packet headers before writing this file.
    """

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"SDF file not found:\n{path}"
        )

    raw = path.read_bytes()

    extra_bytes = len(raw) - IMAGE_BYTES

    print("=" * 70)
    print("FILE")
    print("=" * 70)

    print(f"File:                  {path.name}")
    print(f"File size:             {len(raw):,} bytes")
    print(f"Expected image bytes:  {IMAGE_BYTES:,} bytes")
    print(f"Extra bytes:           {extra_bytes:,} bytes")

    if len(raw) < IMAGE_BYTES:
        raise ValueError(
            f"File is too small for a "
            f"{WIDTH} x {HEIGHT} x {BITS_PER_PIXEL}-bit image."
        )

    return raw


# ============================================================
# CASPEX 12-bit decoder
# ============================================================

def decode_12bit(data):
    """
    Decode CASPEX-SWIR packed 12-bit image data.

    According to the CASPEX camera manual:

        Byte 0 = Pixel_n[7:0]

        Byte 1:
            bits 3..0 = Pixel_n[11:8]
            bits 7..4 = Pixel_n+1[3:0]

        Byte 2 = Pixel_n+1[11:4]

    Therefore:

        Pixel_n =
            byte0 | ((byte1 & 0x0F) << 8)

        Pixel_n+1 =
            (byte2 << 4) | (byte1 >> 4)

    3 input bytes -> 2 x 12-bit pixels.
    """

    if len(data) != IMAGE_BYTES:
        raise ValueError(
            f"Decoder received {len(data):,} bytes, "
            f"expected {IMAGE_BYTES:,}."
        )

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

    return pixels.reshape(
        HEIGHT,
        WIDTH
    )


# ============================================================
# Evaluate candidate image
# ============================================================

def evaluate_image(image):
    """
    Measure spatial continuity of a decoded image.

    This is used only to compare possible starting offsets.

    Lower score means neighboring pixels are, on average,
    more similar.
    """

    x = image.astype(np.int32)

    dx = np.diff(x, axis=1)
    dy = np.diff(x, axis=0)

    median_dx = np.median(
        np.abs(dx)
    )

    median_dy = np.median(
        np.abs(dy)
    )

    mean_dx = np.mean(
        np.abs(dx)
    )

    mean_dy = np.mean(
        np.abs(dy)
    )

    score = median_dx + median_dy

    return {
        "score": score,
        "median_dx": median_dx,
        "median_dy": median_dy,
        "mean_dx": mean_dx,
        "mean_dy": mean_dy,
        "mean": image.mean(),
        "std": image.std(),
    }


# ============================================================
# Search image-data offset
# ============================================================

def find_image_offset(raw):
    """
    Search every possible contiguous image start.

    The current SDF files contain 60 bytes more than the
    expected packed image size.

    We do NOT assume those 60 bytes are all a header.

    Instead, every possible offset is tested with the
    specified CASPEX 12-bit decoder.

    The candidate with the best spatial continuity is returned.

    NOTE:
    This is a diagnostic heuristic, not proof of the SDF format.
    """

    max_offset = len(raw) - IMAGE_BYTES

    print()
    print("=" * 95)
    print("PIXEL DATA OFFSET SEARCH")
    print("=" * 95)

    print(
        f"Testing offsets 0 .. {max_offset}"
    )

    results = []

    for offset in range(max_offset + 1):

        end = offset + IMAGE_BYTES

        data = raw[offset:end]

        if len(data) != IMAGE_BYTES:
            continue

        image = decode_12bit(data)

        metrics = evaluate_image(image)

        results.append({
            "offset": offset,
            **metrics,
        })

    results.sort(
        key=lambda r: r["score"]
    )

    print()
    print(
        "rank  offset   score   med_dx   med_dy"
        "   mean_dx   mean_dy    mean      std"
    )

    print("-" * 95)

    # Show the 20 best candidates
    for rank, result in enumerate(
        results[:20],
        start=1
    ):
        print(
            f"{rank:4d}"
            f"{result['offset']:8d}"
            f"{result['score']:8.1f}"
            f"{result['median_dx']:9.1f}"
            f"{result['median_dy']:9.1f}"
            f"{result['mean_dx']:10.1f}"
            f"{result['mean_dy']:10.1f}"
            f"{result['mean']:9.1f}"
            f"{result['std']:9.1f}"
        )

    best = results[0]

    print()
    print("=" * 70)
    print("BEST OFFSET CANDIDATE")
    print("=" * 70)

    print(f"Offset:       {best['offset']} bytes")
    print(f"Score:        {best['score']:.1f}")
    print(f"Median |dx|:  {best['median_dx']:.1f}")
    print(f"Median |dy|:  {best['median_dy']:.1f}")
    print(f"Mean |dx|:    {best['mean_dx']:.1f}")
    print(f"Mean |dy|:    {best['mean_dy']:.1f}")

    return best["offset"], results


# ============================================================
# Print image statistics
# ============================================================

def print_image_statistics(image):
    """
    Print basic statistics for the decoded image.
    """

    mean = np.mean(image)
    median = np.median(image)
    std = np.std(image)

    saturated = (
        100.0
        * np.mean(image == 4095)
    )

    print()
    print("=" * 70)
    print("IMAGE")
    print("=" * 70)

    print("Shape:       ", image.shape)
    print("Minimum:     ", image.min())
    print("Maximum:     ", image.max())
    print("Mean:        ", mean)
    print("Median:      ", median)
    print("Std:         ", std)
    print("Saturated:   ", f"{saturated:.4f} %")

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
    """
    Display the decoded image and its histogram.
    """

    vmin, vmax = np.percentile(
        image,
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
        origin="upper"
    )

    fig.colorbar(
        im,
        ax=ax_img,
        label="12-bit DN"
    )

    ax_img.set_title(
        f"CHANCES SDF\n"
        f"CASPEX 12-bit decoder, offset {offset}"
    )

    ax_img.set_xlabel(
        "X pixel"
    )

    ax_img.set_ylabel(
        "Y pixel"
    )

    # --------------------------------------------------------
    # Histogram
    # --------------------------------------------------------

    ax_hist.hist(
        image.ravel(),
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

    ax_hist.set_xlim(
        0,
        4096
    )

    ax_hist.set_xlabel(
        "12-bit DN"
    )

    ax_hist.set_ylabel(
        "Number of pixels"
    )

    ax_hist.set_title(
        "Pixel histogram"
    )

    ax_hist.legend()

    # --------------------------------------------------------
    # Statistics box
    # --------------------------------------------------------

    stats = (
        f"Offset: {offset} bytes\n"
        f"Min: {image.min()}\n"
        f"Max: {image.max()}\n"
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
    # Read file
    # --------------------------------------------------------

    raw = read_sdf(filename)

    # --------------------------------------------------------
    # Find candidate start of packed pixels
    # --------------------------------------------------------

    offset, results = find_image_offset(raw)

    # --------------------------------------------------------
    # Extract image bytes
    # --------------------------------------------------------

    data = raw[
        offset:
        offset + IMAGE_BYTES
    ]

    # --------------------------------------------------------
    # Decode using CASPEX specified 12-bit packing
    # --------------------------------------------------------

    image = decode_12bit(data)

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    mean, median, std, saturated = (
        print_image_statistics(image)
    )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    plot_image(
        image=image,
        filename=filename,
        offset=offset,
        mean=mean,
        median=median,
        std=std,
        saturated=saturated
    )