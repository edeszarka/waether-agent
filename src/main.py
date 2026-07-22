import sys

from src.orchestrator import run_agent


def main() -> None:
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = sys.stdin.read().strip()

    if not question:
        print(f"Usage: python -m {__package__ or __name__} <question>")
        sys.exit(1)

    answer, trace_path = run_agent(question)
    print(answer)
    print(f"\n[Trace: {trace_path}]")


if __name__ == "__main__":
    main()
