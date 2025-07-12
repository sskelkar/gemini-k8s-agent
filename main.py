import argparse
from agent import KubernetesDiagnosticAgent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kubernetes Pod Diagnostic Agent")
    parser.add_argument("--namespace", type=str, default="default", help="The namespace to search in.")
    parser.add_argument("--app", type=str, required=True, help="The 'app' label value.")
    parser.add_argument("--country", type=str, required=True, help="The 'country' label value.")
    parser.add_argument("--fleet", type=str, help="The 'fleet' label value (optional).")
    args = parser.parse_args()

    agent = KubernetesDiagnosticAgent(args.namespace, args.app, args.country, args.fleet)
    agent.run()
