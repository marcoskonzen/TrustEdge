from edge_sim_py.components.edge_server import EdgeServer
from edge_sim_py.components.service import Service
from edge_sim_py.components.network_flow import NetworkFlow
from json import dumps


def total_failures(history):
    return len(history)


def mttr(history):
    repair_times = []
    for item in history:
        repair_times.append(item["failure_duration"])

    return sum(repair_times) / len(repair_times) if repair_times else 0


def mtbf(history):
    uptimes_between_failures = []
    for i in range(len(history) - 1):
        uptimes_between_failures.append(history[i + 1]["failure_starts_at"] - history[i]["becomes_available_at"])

    uptime_surplus_considering_last_failure = abs(history[-1]["becomes_available_at"])
    total_uptime = sum(uptimes_between_failures) + uptime_surplus_considering_last_failure

    return total_uptime / len(history) if len(history) > 0 else 0


def failure_rate(history):
    return 1 / mtbf(history) if mtbf(history) != 0 else float("inf")


def conditional_reliability(history, upcoming_instants):
    return 2.71828 ** (-failure_rate(history) * (len(history) + upcoming_instants)) / 2.71828 ** (-failure_rate(history) * len(history))


def trust_edge(parameters: dict = {}):

    server = EdgeServer.first()

    print(f"==== TIME STEP {parameters['current_step']}")
    server_metadata = {
        "object": str(server),
        "status": server.status,
        "available": server.available,
        "total_failures": total_failures(server.failure_model.failure_history),
        "mttr": mttr(server.failure_model.failure_history),
        "mtbf": mtbf(server.failure_model.failure_history),
        "failure_rate": failure_rate(server.failure_model.failure_history),
        "conditional_reliability": conditional_reliability(server.failure_model.failure_history, 20),
        "failure_history['failure_starts_at']": server.failure_model.failure_history[-1]["failure_starts_at"],
        "failure_history['becomes_available_at']": server.failure_model.failure_history[-1]["becomes_available_at"],
        "failure_trace": [server.failure_model.failure_trace[-1][0], server.failure_model.failure_trace[-1][1]],
    }
    print(f"{dumps(server_metadata, indent=4)}")
    print("\n======================\n\n\n")
