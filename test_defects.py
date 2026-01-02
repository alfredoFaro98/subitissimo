from scraper.text_flags import detect_defects

def test_cases():
    tests = [
        # 1) subject="Come nuovo" body="nessun difetto" => 🟢
        ("Come nuovo", "nessun difetto", "🟢"),
        
        # 2) subject="Monitor" body="manca un pezzo" => 🟡
        ("Monitor", "manca un pezzo", "🟡"),

        # 3) subject="Scheda video" body="non funziona" => 🔴
        ("Scheda video", "non funziona", "🔴"),

        # 4) subject="Condizioni perfette" body="ha graffi leggeri" => 🟡
        ("Condizioni perfette", "ha graffi leggeri", "🟡"),
        
        # 5) subject="Perfetto, senza difetti" body="però non si accende" => 🔴
        ("Perfetto, senza difetti", "però non si accende", "🔴"),
    ]

    print("Running 5 Test Cases for Defect Detection:\n")
    all_pass = True
    for subj, body, expected in tests:
        res = detect_defects(subj, body)
        flag = res["flag"]
        status = "PASS" if flag == expected else "FAIL"
        if status == "FAIL": all_pass = False
        print(f"[{status}] exp={expected} got={flag} | '{subj}' + '{body}' -> reason: {res.get('reason')}")

    if all_pass:
        print("\nALL TESTS PASSED ✅")
    else:
        print("\nSOME TESTS FAILED ❌")

if __name__ == "__main__":
    test_cases()
