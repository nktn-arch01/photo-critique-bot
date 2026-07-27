from PIL import Image, IptcImagePlugin
from PIL.ExifTags import TAGS

test_file = "test_input.jpg"

try:
    with Image.open(test_file) as img:
        print("=== 1. EXIF TAGS ===")
        exif = img._getexif()
        if exif:
            for k, v in exif.items():
                tag_name = TAGS.get(k, k)
                val_str = str(v)
                if len(val_str) > 80:
                    val_str = val_str[:80] + "..."
                print(f"  [{tag_name}] ({k}): {val_str}")
        else:
            print("  EXIFデータなし")

        print("\n=== 2. IPTC TAGS ===")
        try:
            iptc = IptcImagePlugin.getiptcinfo(img)
            if iptc:
                for k, v in iptc.items():
                    val_str = str(v)
                    if len(val_str) > 80:
                        val_str = val_str[:80] + "..."
                    print(f"  {k}: {val_str}")
            else:
                print("  IPTCデータなし")
        except Exception as e:
            print(f"  IPTC読み込みエラー: {e}")

        print("\n=== 3. IMG.INFO KEYS (XMP等) ===")
        for k in img.info.keys():
            if k not in ['exif', 'icc_profile']:
                val_str = str(img.info[k])
                if len(val_str) > 100:
                    val_str = val_str[:100] + "..."
                print(f"  {k}: {val_str}")

except Exception as e:
    print(f"ファイルオープンエラー: {e}")
