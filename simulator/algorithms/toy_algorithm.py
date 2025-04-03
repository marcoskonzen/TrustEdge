from edge_sim_py.components.edge_server import EdgeServer
from edge_sim_py.components.service import Service
from edge_sim_py.components.network_flow import NetworkFlow
from json import dumps


def toy_algorithm(parameters: dict = {}):
    server = EdgeServer.first()
    service = Service.first()

    if parameters["current_step"] == 1:
        print(dumps(server.failure_model.failure_trace, indent=4))
        print("\n\n")

    # Start transferring Service 1 to Server 1
    if parameters["current_step"] == 8:
        service.provision(target_server=server)

    if parameters["current_step"] == 12:
        service.server.status = "failing"

    print(f"==== TIME STEP {parameters['current_step']}")
    print(f"{server}. Status: {server.status}. Services: {server.services}")
    print("")
    print(
        f"{service}. Server: {service.server} ({service.server.status}). Available: {service._available}. Being Provisioned: {service.being_provisioned}. Migrations: {service._Service__migrations}"
    )
    print("\n")
    for flow in NetworkFlow.all():
        print(f"{flow}. Status: {flow.status}. Data to transfer: {flow.data_to_transfer}")
    print("\n====================\n")
