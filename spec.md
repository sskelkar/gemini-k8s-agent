# Specification for Kubernetes Diagnostic Agent

## 1. Objective

Create a Python script that acts as a read-only Kubernetes diagnostic agent. The agent runs on a local machine to identify unhealthy pods based on a flexible set of labels and performs a rule-based root cause analysis without modifying any cluster state.

## 2. Core Workflow

The agent follows a three-step, read-only process:

1.  **Identify Unhealthy Pods:**
    *   The agent first identifies all pods matching a user-provided set of labels.
    *   It then analyzes the state of each pod and its containers to flag any that are unhealthy. Conditions for being flagged include:
        *   Pod status is `Pending`, `Failed`, or `Unknown`.
        *   Container states include `CrashLoopBackOff`, `ImagePullBackOff`, or `Error`.
        *   Containers are not `Ready`.

2.  **Gather Forensic Data:**
    *   For each unhealthy pod, the agent automatically collects the standard set of diagnostic information that a human operator would, including:
        *   **Associated Events:** All recent events related to the pod.
        *   **Container Logs:** The logs from the most recent **crashed** (`--previous`) container instance, which is critical for diagnosing crash loops.

3.  **Provide a Rule-Based Diagnosis:**
    *   The agent analyzes the collected data to provide a high-level, plain-language diagnosis for the likely cause of the issue.
    *   The diagnosis is based on a series of rules that check for common failure patterns:
        *   **High-Confidence Reasons:** Checks for `OOMKilled` or `ImagePullBackOff` in the container's state.
        *   **Infrastructure Issues:** Scans pod events for keywords like `FailedScheduling` or `FailedMount`.
        *   **Application Errors:** Scans container logs for common errors like `connection refused` or `file not found`.
        *   **Fallback:** Provides a general diagnosis if no specific rule matches.

## 3. Operational Requirements

*   **Execution Environment:** The script runs on a user's local machine.
*   **Authentication:** It uses a local `kubeconfig` file for cluster authentication.
*   **Safety:**
    *   The agent is **strictly read-only**. It does not perform any actions that modify cluster state.
    *   It includes a safety check to ensure it only connects to a specific, pre-configured cluster name.
*   **Configuration:**
    *   The target `namespace`, `app` label (required), `country` label (required), and `fleet` label (optional) are provided via command-line arguments.

## 4. Out of Scope

*   Automated remediation or any write actions against the cluster.
*   Deployment of the agent as a pod within the Kubernetes cluster.

## 5. Future Milestones

*   **LLM-Powered Analysis:** For complex or ambiguous errors that do not match pre-defined rules, the agent could escalate the issue to a Large Language Model (LLM). It would send the collected forensic data in a detailed prompt and return the LLM's analysis to the user.