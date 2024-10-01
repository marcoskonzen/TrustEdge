from edge_sim_py.components.edge_server import EdgeServer
from json import dumps


def trust_edge(parameters: dict = {}):
    server = EdgeServer.first()

    if parameters["current_step"] == 1:
        print(dumps(server.failure_model.failure_trace, indent=4))
        print("\n\n")

    print(f"==== TIME STEP {parameters['current_step']}")
    print(f"{server}. Status: {server.status}")
    print("")
