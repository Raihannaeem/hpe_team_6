import argparse
import json
import re
from pathlib import Path


DEFAULT_SPEC_JSON = "TC1263_specs.json"

# ---------------- LOAD ----------------
def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="Rank Digi-Key products against a spec JSON file.")
    parser.add_argument(
        "--spec",
        default=DEFAULT_SPEC_JSON,
        help="Path to input spec JSON (absolute or relative to this script directory).",
    )
    return parser.parse_args()


def resolve_spec_path(spec_arg, base_dir):
    spec_path = Path(spec_arg)
    if not spec_path.is_absolute():
        spec_path = base_dir / spec_path
    return spec_path.resolve()


# ---------------- HELPERS ----------------
def extract_float(val):
    if val is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(val))
    return float(match.group()) if match else None


def extract_min_max_float(val):
    if val is None:
        return None, None
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(val))]
    if not nums:
        return None, None
    return min(nums), max(nums)


def parse_temp_range(temp_str):
    if not temp_str:
        return None, None
    nums = re.findall(r"-?\d+", temp_str)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return None, None


def normalize_spec(spec):
    # Keep existing normalized files unchanged.
    if "electrical" in spec and "thermal" in spec:
        return spec

    specs = spec.get("specs", {})
    extra_specs = spec.get("extra_specs", {})

    _, vin_max = extract_min_max_float(specs.get("Input Voltage (Vin)", {}).get("value"))
    _, vout_max = extract_min_max_float(specs.get("Output Voltage (Vout)", {}).get("value"))
    _, iout_max = extract_min_max_float(specs.get("Output Current (Iout)", {}).get("value"))
    _, dropout_v_max = extract_min_max_float(specs.get("Dropout Voltage", {}).get("value"))
    iq_typ = extract_float(specs.get("Quiescent Current (Iq)", {}).get("value"))

    tmin, tmax = parse_temp_range(
        extra_specs.get("Operating Junction Temperature Range", {}).get("value")
    )
    package_type = extra_specs.get("Package Type", {}).get("value")

    normalized = {
        "electrical": {
            "max_input_voltage_V": vin_max,
            "max_output_voltage_V": vout_max,
            "max_output_current_mA": iout_max,
            "dropout_voltage": {
                "max_mV": dropout_v_max * 1000 if dropout_v_max is not None else None
            },
            "quiescent_current": {"typ_uA": iq_typ},
            "PSRR_dB": {}
        },
        "thermal": {
            "min_junction_temperature_C": tmin,
            "max_junction_temperature_C": tmax,
            "thermal_resistance": {}
        },
        "packages": [{"package_type": package_type}] if package_type else []
    }

    return normalized


# ---------------- ORIGINAL ----------------
def build_original_product(spec):
    e = spec.get("electrical", {})
    t = spec.get("thermal", {})
    pkgs = spec.get("packages", [])

    package = None
    if pkgs:
        package = pkgs[0].get("package_type")

    vin = e.get("max_input_voltage_V")
    vout = e.get("max_output_voltage_V")
    iout = e.get("max_output_current_mA")
    dropout_mV = e.get("dropout_voltage", {}).get("max_mV")
    iq = e.get("quiescent_current", {}).get("typ_uA")
    tmin = t.get("min_junction_temperature_C")
    tmax = t.get("max_junction_temperature_C")

    return {
        "parameters": {
            "Voltage - Input (Max)": f"{vin}V" if vin is not None else None,
            "Voltage - Output (Min/Fixed)": f"{vout}V" if vout is not None else None,
            "Current - Output": f"{iout}mA" if iout is not None else None,
            "Voltage Dropout (Max)": f"{dropout_mV/1000}V" if dropout_mV is not None else None,
            "Current - Quiescent (Iq)": f"{iq} uA" if iq is not None else None,
            "Operating Temperature": f"{tmin} to {tmax} C" if tmin is not None and tmax is not None else None,
            "Package / Case": package
        },
        "unit_price": None,
        "stock": None
    }


# ---------------- FEATURE SCORING WITH EXPLANATION ----------------
def score_features_verbose(product, spec):
    params = product.get("parameters", {})
    comparison = {}
    total = 0

    e = spec.get("electrical", {})
    t = spec.get("thermal", {})

    # -------- VOUT --------
    orig = e.get("max_output_voltage_V")
    cand = extract_float(params.get("Voltage - Output (Min/Fixed)"))
    if cand is not None and orig is not None and orig != 0:
        ratio = abs(cand - orig) / orig
        score = 20 if ratio <= 0.01 else 15 if ratio <= 0.03 else 0
    elif cand is not None:
        score = 10
    else:
        score = 0
    comparison["vout"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- IOUT --------
    orig = e.get("max_output_current_mA")
    cand = extract_float(params.get("Current - Output"))
    if cand is not None and orig is not None and orig != 0:
        r = cand / orig
        score = 20 if 1 <= r <= 1.5 else 15 if r <= 2 else 10 if r > 2 else 0
    elif cand is not None:
        score = 10
    else:
        score = 0
    comparison["iout"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- DROPOUT --------
    orig_mV = e.get("dropout_voltage", {}).get("max_mV")
    orig = orig_mV / 1000 if orig_mV is not None else None
    cand = extract_float(params.get("Voltage Dropout (Max)"))
    if cand is not None and orig is not None and orig != 0:
        r = cand / orig
        score = 20 if r <= 1 else 10 if r <= 1.5 else 0
    elif cand is not None:
        score = 5
    else:
        score = 0
    comparison["dropout"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- VIN --------
    orig = e.get("max_input_voltage_V")
    cand = extract_float(params.get("Voltage - Input (Max)"))
    if cand is None:
        score = 0
    elif orig is None or orig == 0:
        score = 10
    else:
        score = 0 if cand < orig else 10 if cand <= 2 * orig else 15
    comparison["vin"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- IQ --------
    orig = e.get("quiescent_current", {}).get("typ_uA")
    cand = extract_float(params.get("Current - Quiescent (Iq)"))
    if cand is not None and orig is not None and orig != 0:
        r = cand / orig
        score = 15 if r <= 1 else 10 if r <= 3 else 5 if r <= 10 else 0
    elif cand is not None:
        score = 8
    else:
        score = 0
    comparison["iq"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- PSRR --------
    orig = e.get("PSRR_dB", {}).get("at_1kHz")
    cand = extract_float(params.get("PSRR"))
    if cand:
        score = 10 if cand >= 70 else 7 if cand >= 50 else 3
    else:
        score = 5
    comparison["psrr"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- TEMP --------
    tmin_o = t.get("min_junction_temperature_C")
    tmax_o = t.get("max_junction_temperature_C")
    tmin_c, tmax_c = parse_temp_range(params.get("Operating Temperature"))

    if tmin_c is not None and tmax_c is not None and tmin_o is not None and tmax_o is not None:
        if tmin_c <= tmin_o and tmax_c >= tmax_o:
            score = 10
        elif tmin_c <= tmin_o:
            score = 7
        elif tmax_c >= tmax_o:
            score = 5
        else:
            score = 0
    elif tmin_c is not None and tmax_c is not None:
        score = 5
    else:
        score = 0

    comparison["temp"] = {"original": [tmin_o, tmax_o], "candidate": [tmin_c, tmax_c], "score": score}
    total += score

    # -------- PRICE --------
    orig = None
    cand = product.get("unit_price")
    if cand is None:
        score = 5
    elif cand < 0.5:
        score = 10
    elif cand < 1:
        score = 7
    else:
        score = 3
    comparison["price"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- STOCK --------
    orig = None
    cand = product.get("stock")
    if cand is None:
        score = 3
    elif cand > 10000:
        score = 5
    elif cand > 1000:
        score = 3
    else:
        score = 1
    comparison["stock"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    # -------- THERMAL RESISTANCE --------
    # Original (take best/representative RθJA)
    thermal_data = spec.get("thermal", {}).get("thermal_resistance", {})

    orig = None
    for pkg in thermal_data.values():
        if isinstance(pkg, dict) and "RθJA_C_per_W" in pkg:
            orig = pkg["RθJA_C_per_W"]
            break

    # Candidate (Digi-Key field)
    cand = extract_float(params.get("Thermal Resistance (Junction to Ambient)"))

    if cand is not None and orig is not None:
        ratio = cand / orig

        if ratio <= 1:
            score = 10  # better
        elif ratio <= 1.5:
            score = 5   # acceptable
        else:
            score = 0   # too high
    else:
        score = 5  # neutral if missing

    comparison["thermal_resistance"] = {
        "original": orig,
        "candidate": cand,
        "score": score
    }

    total += score

    # -------- PACKAGE --------
    packages = spec.get("packages") or [{}]
    orig = packages[0].get("package_type")
    cand = params.get("Package / Case")
    score = 10 if cand and orig and orig.lower() in cand.lower() else 5
    comparison["package"] = {"original": orig, "candidate": cand, "score": score}
    total += score

    return comparison, total


# ---------------- MAIN ----------------
def main(spec_arg):
    base_dir = Path(__file__).resolve().parent
    spec_path = resolve_spec_path(spec_arg, base_dir)
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    spec_raw = load_json(spec_path)
    spec = normalize_spec(spec_raw)
    data = load_json(base_dir / "digikey_results.json")

    products = data.get("products", [])

    original = build_original_product(spec)
    original_comp, original_score = score_features_verbose(original, spec)

    original_feature_scores = {k: v["score"] for k, v in original_comp.items()}

    print("Original Feature Scores:", original_feature_scores)
    print("Original Score:", original_score)

    results = []

    for p in products:
        comp, score = score_features_verbose(p, spec)
        delta = score - original_score

        results.append({
            "description": p.get("description"),
            "feature_comparison": comp,
            "total_score": score,
            "delta": delta
        })

    results.sort(key=lambda x: x["total_score"], reverse=True)

    with open(base_dir / "final_comparison.json", "w") as f:
        json.dump({
            "original_score": original_score,
            "results": results
        }, f, indent=2)

    print("\n Detailed comparison saved to final_comparison.json")


if __name__ == "__main__":
    args = parse_args()
    main(args.spec)