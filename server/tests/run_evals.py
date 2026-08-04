"""Run the behavioral eval suite against the live agent + model.

Usage:
  python -m server.tests.run_evals            run all cases
  python -m server.tests.run_evals --limit 5  smoke run

Each case in eval_cases.jsonl sends `inbound` through agent.respond on a fresh
conversation. A case passes when action, notify_rep, and merchant_interested
all match `expected`. Reply text is generative so it is never string-matched;
for action == reply we only require a non-empty reply (guardrails already
police the content). The freeform `context` field is passed to the model as
stated prior history.

Results stream to logs/eval_results.jsonl; a category summary prints at the end.
"""
import argparse
import json
from pathlib import Path

from .. import agent, config

CASES_PATH = Path(__file__).parent / "eval_cases.jsonl"
RESULTS_PATH = config.ROOT / "logs" / "eval_results.jsonl"

# Evals must never look like a real merchant thread or touch real stores.
config.UPLOAD_LINK = config.UPLOAD_LINK or "https://secure.example.com/upload-test"


def fresh_convo() -> dict:
    return {"phone": "eval", "status": "active", "merchant_first": "Sam",
            "company": "Eval LLC", "record_id": "", "merchant_interested": False,
            "identity_streak": 0, "last_msg_id": "", "messages": []}


def run_case(case: dict) -> dict:
    extra = ""
    if case.get("context"):
        extra = ("For this conversation, treat the following as true prior "
                 "history: " + case["context"])
    try:
        result = agent.respond(fresh_convo(), case["inbound"], extra_system=extra)
    except Exception as exc:
        return {"id": case["id"], "ok": False, "error": str(exc)}

    expected = case["expected"]
    problems = []
    if result["action"] != expected["action"]:
        problems.append(f"action: got {result['action']}, want {expected['action']}")
    if bool(result.get("notify_rep")) != bool(expected.get("notify_rep")):
        problems.append(f"notify_rep: got {result.get('notify_rep')}, "
                        f"want {expected.get('notify_rep')}")
    if bool(result.get("merchant_interested")) != bool(expected.get("merchant_interested")):
        problems.append(f"interested: got {result.get('merchant_interested')}, "
                        f"want {expected.get('merchant_interested')}")
    if expected["action"] == "reply" and result["action"] == "reply" and not result["reply"]:
        problems.append("empty reply")

    return {"id": case["id"], "category": case["category"],
            "difficulty": case.get("difficulty", ""), "ok": not problems,
            "problems": problems, "got_action": result["action"],
            "got_reply": result.get("reply", "")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--resume", action="store_true",
                        help="keep prior non-error results and run only the rest")
    args = parser.parse_args()

    cases = [json.loads(line) for line in
             CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    done: set[str] = set()
    if args.resume and RESULTS_PATH.exists():
        # Keep completed behavioral results; drop infra-error rows so they rerun.
        kept = []
        for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if not rec.get("error"):
                kept.append(line)
                done.add(rec["id"])
        RESULTS_PATH.write_text("\n".join(kept) + ("\n" if kept else ""),
                                encoding="utf-8")
        print(f"resuming: {len(done)} cases already done, "
              f"{len(cases) - len(done)} to run")

    stats: dict[str, list[int]] = {}
    with RESULTS_PATH.open("a" if args.resume else "w", encoding="utf-8") as out:
        for i, case in enumerate(cases, 1):
            if case["id"] in done:
                continue
            result = run_case(case)
            out.write(json.dumps(result) + "\n")
            out.flush()
            passed, total = stats.setdefault(case["category"], [0, 0])
            stats[case["category"]] = [passed + (1 if result["ok"] else 0), total + 1]
            marker = "PASS" if result["ok"] else "FAIL"
            print(f"[{i}/{len(cases)}] {marker} {case['id']} "
                  f"{'; '.join(result.get('problems', []))}", flush=True)

    print("\n=== summary ===")
    total_pass = total_all = 0
    for category, (passed, total) in sorted(stats.items()):
        total_pass += passed
        total_all += total
        print(f"{category}: {passed}/{total}")
    print(f"TOTAL: {total_pass}/{total_all}")


if __name__ == "__main__":
    main()
