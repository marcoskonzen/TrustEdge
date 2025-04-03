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
    """
    Calcula a Confiabilidade Condicional R(T+t,t).
    Como a taxa de falhas (lambda) é constante, utiliza-se a distribuição exponencial.
    R(t) = euler ** (-lambda * t)
    R(T+t,t) = R(T+t) / R(t)
    """
    return 2.71828 ** (-failure_rate(history) * (len(history) + upcoming_instants)) / 2.71828 ** (-failure_rate(history) * len(history))


def trust_edge(parameters: dict = {}):
    print(f"==== TIME STEP {parameters['current_step']}")

    server = EdgeServer.first()
    print(dumps(server.failure_model.failure_history, indent=4))
    print("\n\n\n======================\n\n\n")

    server_metadata = {
        "object": server,
        "total_failures": total_failures(server.failure_model.failure_history),
        "mttr": mttr(server.failure_model.failure_history),
        "mtbf": mtbf(server.failure_model.failure_history),
        "failure_rate": failure_rate(server.failure_model.failure_history),
        "conditional_reliability": conditional_reliability(server.failure_model.failure_history, 20),
    }
    print(f"{server_metadata}")
