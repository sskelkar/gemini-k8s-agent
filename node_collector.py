from kubernetes import client

class NodeCollector:
    def __init__(self, v1_api):
        self.v1_api = v1_api

    def get_node_diagnostics(self):
        """Collects and returns information about cluster nodes and their events."""
        node_info = []
        node_events = []
        try:
            nodes = self.v1_api.list_node().items
            for node in nodes:
                conditions = {c.type: c.status for c in node.status.conditions}
                taints = [f"{t.key}:{t.value}" for t in node.spec.taints] if node.spec.taints else []
                node_info.append({
                    "name": node.metadata.name,
                    "status": conditions.get("Ready", "Unknown"),
                    "conditions": conditions,
                    "allocatable": node.status.allocatable,
                    "capacity": node.status.capacity,
                    "taints": taints
                })

            events = self.v1_api.list_event_for_all_namespaces(field_selector="involvedObject.kind=Node").items
            for event in events:
                node_events.append(f"- {event.last_timestamp} [{event.type}] {event.reason}: {event.message} (Node: {event.involved_object.name})")

        except client.ApiException as e:
            print(f"Error retrieving node diagnostics: {e}")
        return {"nodes": node_info, "events": "\n".join(node_events) if node_events else "No recent node events found."}
