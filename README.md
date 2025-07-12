# Kubernetes Diagnostic Agent

This project provides a read-only, local diagnostic tool that connects to a Kubernetes cluster to identify and analyze unhealthy pods based on a set of labels.

## Architecture

The project is split into two files:

- `agent.py`: A reusable Python library containing the `KubernetesDiagnosticAgent` class, which encapsulates all the diagnostic logic.
- `main.py`: The executable entry point for the tool. It handles command-line argument parsing and uses the `KubernetesDiagnosticAgent` class to run the diagnostics.

## Features

- **Flexible Pod Selection:** Filters pods based on `app` (required), `country` (required), and `fleet` (optional) labels.
- **Health Analysis:** Automatically determines if a pod is healthy or unhealthy by checking its status and the state of its containers (e.g., `CrashLoopBackOff`, `ImagePullBackOff`).
- **Forensic Data Collection:** For any unhealthy pod, it automatically gathers:
    - Recent pod-level events.
    - Logs from any previously crashed containers.
- **Automated Diagnosis:** Provides a rule-based diagnosis and a recommended next step based on the collected data, helping to quickly identify common issues like `OOMKilled`, `ImagePullBackOff`, or application-level errors in the logs.
- **Safety First:**
    - The agent is **strictly read-only**.
    - It includes a safety check to ensure it only connects to the cluster name specified in its configuration.

## Prerequisites

- Python 3
- `pip` for Python package installation
- Access to a Kubernetes cluster with a valid `kubeconfig` file.

## Installation

1.  **Clone the repository or download the `agent.py` and `main.py` files.**

2.  **Install the required Python library:**

    ```bash
    pip install kubernetes
    ```

## Configuration

Before running, you must configure two variables at the top of the `agent.py` script:

- `EXPECTED_CLUSTER_NAME`: A critical safety feature. The script will abort if the active context in your `kubeconfig` does not match this name. **Default:** `"staging"`.
- `KUBECONFIG_PATH`: The path to your `kubeconfig` file. **Default:** `"~/.kube_tool/staging-eu"`.

**Example Configuration in `agent.py`:**
```python
# --- Configuration ---
EXPECTED_CLUSTER_NAME = "staging"
KUBECONFIG_PATH = "~/.kube_tool/staging-eu"
```

## How to Run

Execute the `main.py` script from your terminal, providing the required and optional arguments.

### Arguments

- `--app` (required): The value for the `app` label.
- `--country` (required): The value for the `country` label.
- `--fleet` (optional): The value for the `fleet` label.
- `--namespace` (optional): The Kubernetes namespace to search in. Defaults to `default`.

### Example Usage

**1. Basic search for unhealthy pods:**

```bash
python3 main.py --app dashboard --country kr2 --namespace hurrier
```

**2. Search including the optional `fleet` label:**

```bash
python3 main.py --app dashboard --country kr2 --fleet api --namespace hurrier
```
