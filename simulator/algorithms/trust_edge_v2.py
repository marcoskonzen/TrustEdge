# Importing EdgeSimPy components
from edge_sim_py import *

# Importing native Python modules/packages
from json import dumps

# Importing helper functions
from simulator.helper_functions import *

# Importing EdgeSimPy extensions
from simulator.extensions import *

# Importing logging modules
import math
from datetime import datetime

"""TRUST EDGE ALGORITHM"""

def trust_edge_v2(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge_v2 (sem migração proativa).
    
    Args:
        parameters (dict): Parâmetros da simulação.
    """

    # Checking if there are users making access requests to applications
    current_step = parameters.get("current_step") - 1
    apps_metadata = []

    for user in User.all():
        if is_making_request(user, current_step):
            # For each user making requests, collect application information
            for app in user.applications:
                app_attrs = {
                    "object": app,
                    "delay_sla": app.users[0].delay_slas[str(app.id)],
                    "delay_score": get_application_delay_score(app),
                    "intensity_score": get_application_access_intensity_score(app),
                    "demand_resource": get_normalized_demand(app.services[0]),
                }
                apps_metadata.append(app_attrs)


    min_and_max_app = find_minimum_and_maximum(metadata=apps_metadata)
    
    apps_metadata = sorted(
    apps_metadata, 
    key=lambda app: (
        get_norm(metadata=app, attr_name="delay_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        get_norm(metadata=app, attr_name="intensity_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        (1 - get_norm(metadata=app, attr_name="demand_resource", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]))
    ), reverse=True
    )

    # Iterating over the sorted list of applications for provisioning
    for app_metadata in apps_metadata:
        app = app_metadata["object"]
        user = app.users[0]
        service = app.services[0]

        print(f"\n[LOG] Aplicações com requisições no step {current_step}:")
        print(f" - Aplicação {app_metadata['object'].id}: Delay Score={app_metadata['delay_score']} e SLA={app_metadata['delay_sla']}")
        print(f"[LOG] Demanda da aplicação: CPU={service.cpu_demand}, RAM={service.memory_demand}")

        # Getting the list of edge server candidates to host the service
        edge_servers = get_host_candidates(user=user, service=service)

        if not edge_servers:
            print(f"[LOG] Nenhum servidor disponível para hospedar o serviço da aplicação.")
            
        else:

            # Finding the minimum and maximum values for the edge server attributes
            min_and_max = find_minimum_and_maximum(metadata=edge_servers)

            # Sorting edge server host candidates based on the number of SLA violations they
            # would cause to the application and their trust cost
            edge_servers = sorted(
                edge_servers,
                key=lambda s: (
                    s["sla_violations"],
                    get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
                    get_norm(metadata=s, attr_name="amount_of_uncached_layers", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
                    get_norm(metadata=s, attr_name="overall_delay", min=min_and_max["minimum"], max=min_and_max["maximum"]),
                    
                ),
            )

            # Greedily iterating over the list of edge servers to find a host for the service
            for edge_server_metadata in edge_servers:
                edge_server = edge_server_metadata["object"]
                free_capacity = edge_server_metadata["free_capacity"]

                # print("\n[LOG] Edge Server candidates for hosting the service:")
                # print(edge_server_metadata)
                
                if edge_server == service.server:
                    print(f"[LOG] Service is already hosted on Edge Server {edge_server}. Skipping...")
                    break

                print(f"[LOG] Tentando provisionar em {edge_server}. CPU demandada: {edge_server.cpu_demand}/{edge_server.cpu}, RAM demandada: {edge_server.memory_demand}/{edge_server.memory}. Disk demandada: {edge_server.disk_demand}/{edge_server.disk}. Free capacity: {free_capacity}")

                # Provisioning the service on the best edge server found it it has enough resources
                if edge_server.has_capacity_to_host(service):
                    print(f"[LOG] Edge Server host service before provisioning: {service.server}")
                    
                    provision(user=user, application=app, service=service, edge_server=edge_server)
                    
                    print(f"[LOG] Provisioning {service} of {app} for {user} on {edge_server} at step {current_step}")
                    print("\n")
                    
                    break

    update_user_perceived_downtime_for_current_step()
    
    # Collecting SLA violations for the current step
    collect_sla_violations_for_current_step()

    # Collecting infrastructure usage metrics for the current step
    collect_infrastructure_metrics_for_current_step()

    # Displaying reliability metrics
    #display_reliability_metrics(parameters=parameters)

    # Displaying simulation metrics
    display_simulation_metrics(simulation_parameters=parameters)

    # print(f"\n[LOG] Applications with requests on step {current_step}:")
    # for app in apps_metadata:
    #     print(f" - Application {app['object'].id}: Delay Score={app['delay_score']}")

    # print(f"\n[LOG] Users making requests on step {current_step}:")
    # print(users_making_requests)
    # print("\n")

    # Displaying detailed information about applications, their servers and users
    #display_application_info()

    # Register the current state of all entities for diagnosis
    #print("[DEBUG] Chamando log_entities_state")
    #display_log_entities_state(parameters)
