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

def trust_edge_v1(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge.
    
    Args:
        parameters (dict): Parâmetros da simulação.
    """

    # Verificando se existem usuários fazendo requisição de acesso à aplicação
    current_step = parameters.get("current_step") - 1
    apps_metadata = []
    for user in User.all():
        if is_making_request(user, current_step):
            # Para cada usuário fazendo requisição, coletar informações das aplicações
            for app in user.applications:
                app_attrs = {
                    "object": app,
                    "delay_sla": app.users[0].delay_slas[str(app.id)],
                    "delay_score": get_application_delay_score(app),
                    "intensity_score": get_application_access_intensity_score(app),
                }
                apps_metadata.append(app_attrs)

    apps_metadata = sorted(
        apps_metadata,
        key=lambda app: app["delay_score"],
        reverse=True
        )

    # Iterando sobre a lista ordenada das aplicações para provisionamento
    for app_metadata in apps_metadata:
        app = app_metadata["object"]
        user = app.users[0]
        service = app.services[0]

        print(f"\n[LOG] Aplicações com requisições no step {current_step}:")
        print(f" - Aplicação {app_metadata['object'].id}: Delay Score={app_metadata['delay_score']} e SLA={app_metadata['delay_sla']}")
        print(f"[LOG] Demanda da aplicação: CPU={service.cpu_demand}, RAM={service.memory_demand}")

        # Obtendo a lista de servidores de borda candidatos para hospedar o serviço
        edge_servers = get_host_candidates(user=user, service=service)

        # Finding the minimum and maximum values for the edge server attributes
        min_and_max = find_minimum_and_maximum(metadata=edge_servers)

        # Sorting edge server host candidates based on the number of SLA violations they
        # would cause to the application and their trust cost
        edge_servers = sorted(
            edge_servers,
            key=lambda s: (
                get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]),
            ),
        )

        # edge_servers = sorted(
        #     edge_servers,
        #     key=lambda s: (
        #         s["sla_violations"],
        #         get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]),
        #     ),
        # )

        # Greedily iterating over the list of edge servers to find a host for the service
        for edge_server_metadata in edge_servers:
            edge_server = edge_server_metadata["object"]

            # print("\n[LOG] Edge Server candidates for hosting the service:")
            # print(edge_server_metadata)
            
            if edge_server == service.server:
                print(f"[LOG] Service is already hosted on Edge Server {edge_server}. Skipping...")
                break

            print(f"[LOG] Tentando provisionar em {edge_server}. CPU demandada: {edge_server.cpu_demand}/{edge_server.cpu}, RAM demandada: {edge_server.memory_demand}/{edge_server.memory}. Disk demandada: {edge_server.disk_demand}/{edge_server.disk}")

            # Provisioning the service on the best edge server found it it has enough resources
            if edge_server.has_capacity_to_host(service):
                print(f"[LOG] Edge Server host service before provisioning: {service.server}")
                
                provision(user=user, application=app, service=service, edge_server=edge_server)
                
                print(f"[LOG] Provisioning {service} of {app} for {user} on {edge_server} at step {current_step}")
                print("\n")
                
                break

            # else:
            #     raise Exception(f"{app} could not be provisioned.")

    update_user_perceived_downtime_for_current_step()
    
    # Collecting SLA violations for the current step
    collect_sla_violations_for_current_step()

    # Collecting infrastructure usage metrics for the current step
    collect_infrastructure_metrics_for_current_step()
    
    # Exibindo métricas de confiabilidade
    #display_reliability_metrics(parameters=parameters)

    # Exibindo métricas de simulação
    display_simulation_metrics(simulation_parameters=parameters)

    # print(f"\n[LOG] Aplicações com requisições no step {current_step}:")
    # for app in apps_metadata:
    #     print(f" - Aplicação {app['object'].id}: Delay Score={app['delay_score']}")

    # print(f"\n[LOG] Usuários fazendo requisições no step {current_step}:")
    # print(users_making_requests)
    # print("\n")

    # Exibindo informações detalhadas das aplicações, seus servidores e usuários
    #display_application_info()

    # Registrar o estado atual de todas as entidades para diagnóstico
    #print("[DEBUG] Chamando log_entities_state")
    #display_log_entities_state(parameters)