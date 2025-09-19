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
                    (1 - get_norm(metadata=s, attr_name="free_capacity", min=min_and_max["minimum"], max=min_and_max["maximum"])),
                ),
            )
            
            # edge_servers = sorted(
            #     edge_servers,
            #     key=lambda s: (
            #         get_norm(metadata=s, attr_name="sla_violations", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            #         get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            #         get_norm(metadata=s, attr_name="amount_of_uncached_layers", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            #         get_norm(metadata=s, attr_name="free_capacity", min=min_and_max["minimum"], max=min_and_max["maximum"]),
            #     ),
            # )

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


""" CALCULATING RELIABILITY METRICS AND SCORES """

def get_server_total_failures(server):
    """Retorna o número total de falhas de um servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        int: Número total de falhas registradas.
    """
    history = server.failure_model.failure_history
    return len(history)


def get_server_mttr(server):
    """Calcula o Mean Time To Repair (MTTR) do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo médio para reparo (MTTR) ou 0 se não houver falhas.
    """
    history = server.failure_model.failure_history
    repair_times = []
    for failure_occurrence in history:
        repair_times.append(failure_occurrence["becomes_available_at"] - failure_occurrence["failure_starts_at"])

    return sum(repair_times) / len(repair_times) if repair_times else 0


def get_server_downtime_history(server):
    """Calcula o tempo total de inatividade do servidor considerando todo o histórico.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de inatividade (downtime) do servidor de todo o histórico.
    """
    total_downtime = 0
    
    for failure_occurrence in server.failure_model.failure_history:
        # Calcula o tempo de downtime para cada falha no histórico
        failure_start = failure_occurrence["failure_starts_at"]
        failure_end = failure_occurrence["becomes_available_at"]
        total_downtime += failure_end - failure_start

    return total_downtime


def get_server_uptime_history(server):
    """Calcula o tempo total de atividade do servidor considerando todo o histórico.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de atividade (uptime) do servidor de todo o histórico.
    """
    # Se não houver histórico de falhas, consideramos todo o tempo como uptime
    if not server.failure_model.failure_history:
        return float("inf")  # Retorna infinito se nunca falhou
    
    # Calcula o tempo total desde o início do histórico até o momento atual, contando o 0.
    total_time_span = abs(getattr(server.failure_model, 'initial_failure_time_step') - (server.model.schedule.steps + 1)) + 1
    total_downtime = get_server_downtime_history(server=server)

    total_uptime = total_time_span - total_downtime

    return total_uptime


def get_server_downtime_simulation(server):
    """Calcula o tempo total de inatividade do servidor durante a simulação.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de inatividade (downtime) do servidor durante a simulação.
        
    Note:
        O step 1 (primeiro step) não é considerado pois é usado apenas para inicialização.
        As métricas de simulação começam a contar a partir do step 2.
    """
    current_step = server.model.schedule.steps
    
    total_downtime = 0
    
    for available in server.available_history:
        if available is False:
            total_downtime += 1
    
    return total_downtime


def get_server_uptime_simulation(server):
    """Calcula o tempo total de atividade do servidor durante a simulação.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de atividade (uptime) do servidor durante a simulação.
        
    Note:
        O step 1 (primeiro step) não é considerado pois é usado apenas para inicialização.
        As métricas de simulação começam a contar a partir do step 2.
    """

    total_uptime = 0

    for available in server.available_history:
        if available:
            total_uptime += 1

    return total_uptime


def get_server_mtbf(server):
    """Calcula o Mean Time Between Failures (MTBF) do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo médio entre falhas (MTBF) ou infinito se não houver falhas.
    """
    number_of_failures = len(server.failure_model.failure_history)
    
    if number_of_failures == 0:
        return float("inf")  # Retorna infinito se não houver falhas
        
    return get_server_uptime_history(server) / number_of_failures


def get_server_failure_rate(server):
    """Calcula a taxa de falha do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Taxa de falha (failures/time unit) ou 0 se não houver falhas.
    """
    mtbf = get_server_mtbf(server)
    return 1 / mtbf if mtbf != 0 and mtbf != float("inf") else 0


def get_server_conditional_reliability(server, upcoming_instants):
    """Calcula a confiabilidade condicional do servidor para instantes futuros.
    
    Args:
        server (EdgeServer): O objeto servidor.
        upcoming_instants (int): Número de instantes futuros a considerar.
        
    Returns:
        float: Valor da confiabilidade condicional (entre 0 e 1).
    """
    server_failure_rate = get_server_failure_rate(server)
    
    if server_failure_rate == 0:
        return 1.0 * 100  # Confiabilidade máxima se não há taxa de falha
        
    # Usando math.exp para maior precisão nos cálculos exponenciais
    return (math.exp(-server_failure_rate * upcoming_instants)) * 100


def get_application_downtime(application):
    """Calcula o tempo de downtime da aplicação durante a simulação.
    
    Args:
        application (Application): O objeto aplicação.
        
    Returns:
        int: Número de timesteps onde a aplicação esteve indisponível.
        
    Note:
       
    """

    downtime_count = 0

    for availability_status in application.availability_history:
        if availability_status is False:
            downtime_count += 1

    return downtime_count


def get_application_uptime(application):
    """Calcula o tempo de uptime da aplicação durante a simulação.
    
    Args:
        application (Application): O objeto aplicação.
        
    Returns:
        int: Número de timesteps onde a aplicação esteve disponível.
        
    Note:
        
    """
    
    uptime_count = 0
    
    for availability_status in application.availability_history:
        if availability_status is True:
            uptime_count += 1
        
    return uptime_count


def get_user_perceived_downtime(application):
    """Calcula o tempo de downtime percebido pelo usuário para uma aplicação específica.
    
    Args:
        user (User): O objeto usuário.
        application_id (str): O ID da aplicação.
        
    Returns:
        int: O número de timesteps onde o usuário percebeu downtime.
        
    Note:
        O downtime percebido é baseado no histórico de downtime da aplicação.
        Se o usuário não tiver histórico suficiente, retorna 0.
    """
    
    perceived_downtime = sum(1 for status in application.downtime_history if status)
    return perceived_downtime


def get_time_since_last_repair(server):
    """Calcula o tempo desde o último reparo concluído do servidor.
    
    Realiza um cálculo preciso considerando:
    1. Se o servidor está atualmente em falha (retorna 0)
    2. O histórico de falhas passadas do servidor
   
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: 0 se o servidor estiver em falha (failing ou booting),
              infinito se nunca falhou,
              ou o tempo de operação desde o último reparo.
    """
    # Verificar se o servidor tem histórico de falhas
    if not server.failure_model.failure_history:
        return float("inf")  # Nunca falhou, então o tempo é "infinito"
    
    # Se o servidor está em falha (failing ou booting),
    # retornar 0 imediatamente
    current_step = server.model.schedule.steps
    if is_ongoing_failure(server, current_step):
        return 0
    
    else:
    
        # Ordenar o histórico pelo momento de reparo (becomes_available_at) do mais recente para o mais antigo
        sorted_history = sorted(
            server.failure_model.failure_history, 
            key=lambda x: x["becomes_available_at"], 
            reverse=True
        )
        
        # Encontrar o reparo mais recente que ocorreu antes do tempo atual
        last_repair = None
        for failure in sorted_history:
            # Considerar apenas reparos concluídos antes do tempo atual
            if failure["becomes_available_at"] <= current_step:
                last_repair = failure
                break
        
        # Calcular o tempo desde o último reparo e garantir que seja não-negativo
        time_since_repair = current_step + 1 - last_repair["becomes_available_at"]
        return time_since_repair


def get_application_delay_score(app: object) -> float:
    """Calculates the application delay score considering the number application's SLA and the number of edge servers close enough
    to the application's user that could be used to host the application's services without violating the delay SLA.

    Args:
        app (object): Application whose delay score will be calculated.

    Returns:
        app_delay_score (float): Application's delay score.
    """
    # Gathering information about the application
    delay_sla = app.users[0].delay_slas[str(app.id)]
    user_switch = app.users[0].base_station.network_switch

    # Gathering the list of hosts close enough to the user that could be used to host the services without violating the delay SLA
    edge_servers_that_dont_violate_delay_sla = 0
    
    # Cria uma lista com servidores disponíveis
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    
    # Itera sobre os servidores disponíveis e verifica quantos violam o SLA de delay
    for edge_server in available_servers:
        if calculate_path_delay(origin_network_switch=user_switch, target_network_switch=edge_server.network_switch) <= delay_sla:
            edge_servers_that_dont_violate_delay_sla += 1

    if edge_servers_that_dont_violate_delay_sla == 0:
        app_delay_score = 0
    else:
        app_delay_score = 1 / ((edge_servers_that_dont_violate_delay_sla * delay_sla) ** (1 / 2))

    return app_delay_score


def get_application_access_intensity_score(app: object) -> float:
    """Calcula o score de intensidade de acesso da aplicação baseado no padrão de acesso do usuário.
    
    Aplicações com maior duração de acesso e menores intervalos têm maior prioridade.
    
    Args:
        app (object): Application object.
        
    Returns:
        float: Score de intensidade de acesso (maior = mais prioritário).
    """
    user = app.users[0]
    
    # Buscar o padrão de acesso para esta aplicação
    access_pattern = user.access_patterns[str(app.id)]
    
    # Obter valores de duração e intervalo (usar o primeiro valor da lista)
    duration = access_pattern.duration_values[0] if access_pattern.duration_values else 1
    interval = access_pattern.interval_values[0] if access_pattern.interval_values else 1
    
    # Calcular score: quanto maior a duração e menor o intervalo, maior o score
    # Usar log para suavizar diferenças extremas
    import math
    
    # Fórmula: duration / interval * fator de normalização
    base_score = duration / interval
    
    # Aplicar log para suavizar + adicionar fator multiplicativo
    intensity_score = math.log(1 + base_score) * 10
    
    return intensity_score


def get_server_trust_cost(server):
    """Calcula um custo de risco instantâneo para o servidor.

    O custo é calculado multiplicando-se:
    1. Taxa de falhas (quanto maior, pior)
    2. Proporção do tempo desde o último reparo em relação ao MTBF
       (quanto maior essa proporção, maior o risco de uma falha iminente)

    Um servidor com menor custo de risco é mais confiável porque:
    - Tem menor taxa de falhas historicamente
    - Ainda não se aproximou de seu MTBF desde o último reparo
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Custo de risco (quanto menor, melhor - indica maior confiabilidade).
              Servidores que nunca falharam retornam 0 (máxima confiabilidade).
    """
    # Obter os valores dos parâmetros
    failure_rate = get_server_failure_rate(server)
    time_since_repair = get_time_since_last_repair(server)
    mtbf = get_server_mtbf(server)
    
    # Caso especial: servidor nunca falhou ou tem dados históricos insuficientes
    if failure_rate == 0 or mtbf == float("inf"):
        return 0

    if time_since_repair == 0:
        return float("inf")  # Risco máximo se o servidor está atualmente em falha  

    # Calcular a proporção do tempo desde o último reparo em relação ao MTBF
    proportion = time_since_repair / mtbf
    

    # Cálculo: multiplicar a taxa de falha pela proporção do tempo desde reparo/MTBF
    # Quanto menor o resultado, menor o risco de falha (mais confiável)
    risk_cost = failure_rate * proportion

    return risk_cost


def get_host_candidates(user: object, service: object) -> list:
    """Get list of host candidates for hosting services of a given user.
    Args:
        user (object): User object.
    Returns:
        host_candidates (list): List of host candidates.
    """
    
    app_delay = user.delays[str(service.application.id)] if user.delays[str(service.application.id)] is not None else 0

    host_candidates = []
    
    available_servers = [s for s in EdgeServer.all() if s.status == "available" and get_normalized_free_capacity(s) > 0]
    for edge_server in available_servers:
        additional_delay = calculate_path_delay(
            origin_network_switch=user.base_station.network_switch, target_network_switch=edge_server.network_switch
        )
        overall_delay = app_delay + additional_delay
        sla_violations = 1 if overall_delay > user.delay_slas[str(service.application.id)] else 0

        # Gathering the edge server's trust cost
        trust_cost_edge_server = get_server_trust_cost(edge_server)

        # Gathering the edge server's power consumption cost based on its CPU usage
        static_power_consumption = edge_server.power_model_parameters["static_power_percentage"]
        consumption_per_core = edge_server.power_model_parameters["max_power_consumption"] / edge_server.cpu
        power_consumption = consumption_per_core + static_power_consumption * (1 - sign(edge_server.cpu_demand))

        # Gathering the list of container layers used by the service's image
        service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
        service_layers = [ContainerLayer.find_by(attribute_name="digest", attribute_value=digest) for digest in service_image.layers_digests]

        # Calculating the aggregated size of container layers used by the service's image that are NOT cached in the candidate server
        layers_downloaded = [layer for layer in edge_server.container_layers]
        amount_of_uncached_layers = 0
        for layer in layers_downloaded:
            if not any(layer.digest == service_layer.digest for service_layer in service_layers):
                amount_of_uncached_layers += layer.size

        if amount_of_uncached_layers == 0:
            score_amount_of_uncached_layers = 1  # To avoid zero values in the sorting process
        else:
            score_amount_of_uncached_layers = 1 / amount_of_uncached_layers
        
        host_candidates.append(
            {
                "object": edge_server,
                "sla_violations": sla_violations,
                "trust_cost": trust_cost_edge_server,
                "power_consumption": power_consumption,
                "overall_delay": overall_delay,
                "amount_of_uncached_layers": amount_of_uncached_layers,
                "score_amount_of_uncached_layers": score_amount_of_uncached_layers,
                "free_capacity": get_normalized_free_capacity(edge_server),
            }
        )

    return host_candidates


def is_ongoing_failure(server, current_step=None):
    """Verifica se o servidor tem uma falha em andamento no momento atual.
    
    Args:
        server (EdgeServer): O objeto servidor.
        current_time (int, opcional): O tempo atual da simulação. 
                                    Se não fornecido, será calculado baseado no step atual.
    
    Returns:
        bool: True se houver uma falha em andamento, False caso contrário.
    """
    # Se o tempo não foi fornecido, calcular baseado no step atual
    if current_step is None:
        current_step = server.model.schedule.steps
        
    # Verificar se o servidor tem histórico de falhas
    if not server.failure_model.failure_history:
        return False
        
    # Aplanar o failure_history para facilitar a busca
    flatten_failure_trace = [item for failure_group in server.failure_model.failure_trace for item in failure_group]
    
    # Procurar por uma falha que inclua o tempo atual
    ongoing_failure = next(
        (
            failure
            for failure in flatten_failure_trace
            if failure["failure_starts_at"] <= current_step and current_step < failure["becomes_available_at"]
        ),
        None,
    )
    
    return ongoing_failure is not None


def is_making_request(user, current_step):
    """Verifica se um usuário está fazendo uma requisição em um determinado step.

    Args:
        user (User): O objeto usuário.
        current_step (int): O step atual da simulação.

    Returns:
        bool: True se o usuário está fazendo uma requisição, False caso contrário.
    """
    for app in user.applications:
        last_access = user.access_patterns[str(app.id)].history[-1]
        if current_step == last_access["start"]:
            return True
    return False


def display_log_entities_state(parameters: dict = {}):
    """
    Função para mostrar o status de servidores, aplicações e serviços em cada step da simulação.
    
    Reflete apenas os status coletados e atualizados pelos extensions (edge_server_extensions.py 
    e application_extensions.py), sem fazer cálculos ou modificações.
    
    Args:
        model: O objeto modelo da simulação.
        
    Note:
      
    """
    try:
        # Obter o step atual

        current_step = parameters.get("current_step")

        
        print(f"\n[LOG] ===== STATUS - STEP {current_step} =====")
        
        # Status dos servidores (coletado do edge_server_extensions.py)
        print("\n--- SERVIDORES ---")
        for server in EdgeServer.all():
            # Apenas refletir os status já definidos pelos extensions
            _available = getattr(server, 'available', 'N/A')
            _status = getattr(server, 'status', 'N/A')
            
            # Verificar se há falha em andamento (para informação)
            failure_info = f", OngoingFailure={is_ongoing_failure(server)}"

            print(f"Servidor {server.id}: Available={_available}, Status={_status}{failure_info}")
        
        # Status dos serviços (sincronizados via update_service_availability())
        print("\n--- SERVIÇOS ---")
        for service in Service.all():
            # Apenas refletir os status já sincronizados
            service_available = getattr(service, '_available', 'N/A')
            server_id = service.server.id if hasattr(service, 'server') and service.server else 'N/A'
            server_available = getattr(service.server, 'available', 'N/A') if hasattr(service, 'server') and service.server else 'N/A'
            
            print(f"Serviço {service.id}: Available={service_available}, Servidor={server_id} (Available={server_available})")

        # Status das aplicações (coletado do application_extensions.py)
        print("\n--- APLICAÇÕES ---")
        for application in Application.all():
            # Apenas refletir o status já definido pelos extensions
            availability_status = getattr(application, 'availability_status', 'N/A')
            
            # Mostrar histórico apenas para debug, mas métricas só contam a partir do step 2
            #if hasattr(application, 'availability_history'):
            uptime = get_application_uptime(application)
            downtime = get_application_downtime(application)
            uptime_info = f"Uptime={uptime}"
            downtime_info = f"Downtime={downtime}"
            # else:
            #     uptime_info = "Histórico: vazio"
            #     downtime_info = "não disponível"
            
            print(f"Aplicação {application.id}: Status={availability_status}, {uptime_info}, {downtime_info}")
    
        print(f"[LOG] ===== FIM STATUS - STEP {current_step} =====\n")

    except Exception as e:
        print(f"[LOG ERROR] Erro ao mostrar status: {str(e)}")
        import traceback
        traceback.print_exc()


def display_simulation_metrics(simulation_parameters: dict):
    """
    Exibe métricas detalhadas da simulação.
    
    Note:
        - Métricas de simulação (uptime/downtime) só contam a partir do step 2
        - Métricas históricas (MTBF, MTTR, etc.) são baseadas em dados pré-simulação
        - Step 1 é considerado inicialização e não contabilizado nas métricas de simulação
    """
    # Verificar se estamos no step de inicialização
    current_step = simulation_parameters.get("current_step")

    # Métricas detalhadas de servidor
    server_metrics = {}
    for server in EdgeServer.all():
        # Métricas históricas (sempre calculadas, baseadas em dados pré-simulação)
        reliability = get_server_conditional_reliability(server, upcoming_instants=1)
        trust_cost = get_server_trust_cost(server)
        time_since_repair = get_time_since_last_repair(server)


        history_downtime = get_server_downtime_history(server)
        history_uptime = get_server_uptime_history(server)
        sim_uptime = get_server_uptime_simulation(server)
        sim_downtime = get_server_downtime_simulation(server)
        
        server_metrics[f"Server {server.id}"] = {
            "Risk Cost": trust_cost,
            "Simulation Uptime": sim_uptime,
            "Simulation Downtime": sim_downtime,
            "History Uptime": history_uptime,
            "History Downtime": history_downtime,
            "MTBF": get_server_mtbf(server),
            "MTTR": get_server_mttr(server),
            "Failure Rate": get_server_failure_rate(server),
            "Reliability": reliability,
            "Time Since Last Repair": time_since_repair,
            "Total Failures": get_server_total_failures(server)
        }
    
    # Métricas detalhadas de aplicações
    application_metrics = {}
    for application in Application.all():
        app_uptime = get_application_uptime(application)
        app_downtime = get_application_downtime(application)
            
        application_metrics[f"Application {application.id}"] = {
            "Uptime": app_uptime,
            "Downtime": app_downtime
        }
    
    # Métricas detalhadas de usuários
    user_metrics = {}
    for user in User.all():
        user_entry = {}
        for application in user.applications:
            perceived_downtime = get_user_perceived_downtime(application)
            user_entry[f"Application {application.id} Perceived Downtime"] = perceived_downtime
        user_metrics[f"User {user.id}"] = user_entry

    metrics = {
        "Simulation Parameters": simulation_parameters,
        "Number of Applications/Services/Users": f"{Application.count()}/{Service.count()}/{User.count()}",
        "Server Metrics": server_metrics,
        "Application Metrics": application_metrics,
        "User Perceived Downtime Metrics": user_metrics,
    }
    
    print(dumps(metrics, indent=4))


def display_reliability_metrics(parameters: dict = {}):
    """Exibe um resumo das métricas de confiabilidade de todos os servidores.
    Esta função é útil para análises durante a execução da simulação.
    
    Os servidores são ordenados pelo custo de risco (crescente), 
    onde valores menores indicam servidores mais confiáveis.

    O custo de risco é calculado como: taxa_falha * (tempo_desde_reparo/MTBF)
    Quanto mais próximo o servidor estiver de seu tempo médio entre falhas,
    maior será seu custo de risco.
    
    Args:
        model (Model, opcional): O objeto modelo da simulação para obter o step atual.
    """


    # Obter o step atual corrigido
    current_step = parameters.get("current_step")
    
    print("\n\n")
    print(f"Step: {current_step}")
    print("==========================================================================")
    print("==================== MÉTRICAS DOS SERVIDORES DISPONÍVEIS =================")
    print("==========================================================================")
    

    # Cria uma lista com servidores disponíveis
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]

    # Ordenar por custo de risco (crescente) - servidores mais confiáveis primeiro (menor custo)
    servers = sorted(available_servers, key=lambda s: get_server_trust_cost(s))

    # Cabeçalho da tabela
    print(f"{'Rank':^5}|{'ID':^5}|{'Status':^10}|{'Custo do Risco':^12}|{'Taxa Falha':^12}|{'T.Últ.Rep':^10}|{'MTBF':^10}|{'MTTR':^8}|{'Falhas':^8}|{'Conf. short_lived':^18}|{'Conf. long_lived':^18}|")
    print(f"{'':^5}|{'':^5}|{'':^10}|{'(F×T/MTBF)':^12}|{'':^12}|{'':^10}|{'':^10}|{'':^8}|{'':^8}|{'':^18}|{'':^18}|")
    print("-" * 125)

    for rank, server in enumerate(servers, 1):
        server_id = server.id
        server_status = getattr(server, 'status', 'N/A')
        failures = get_server_total_failures(server)
        mttr = get_server_mttr(server)
        mtbf = get_server_mtbf(server)
        risk_cost = get_server_trust_cost(server)
        time_since_repair = get_time_since_last_repair(server)
        failure_rate = get_server_failure_rate(server)
        risk_short_lived = f"{get_server_conditional_reliability(server, upcoming_instants=10):.2f}"
        risk_long_lived = f"{get_server_conditional_reliability(server, upcoming_instants=60):.2f}"

        # Formatação especial para MTBF e tempo desde último reparo infinito
        if mtbf == float("inf"):
            mtbf_str = "∞"
        else:
            mtbf_str = f"{mtbf:.2f}"
            
        if time_since_repair == float("inf"):
            time_repair_str = "Nunca"
        else:
            time_repair_str = f"{time_since_repair:.2f}"

        # Formatação especial para risk cost
        if risk_cost == 0:
            risk_cost_str = "Mínimo"
        else:
            risk_cost_str = f"{risk_cost:.4f}"

        print(f"{rank:^5}|{server_id:^5}|{server_status:^10}|{risk_cost_str:^12}|{failure_rate:^12.6f}|{time_repair_str:^10}|{mtbf_str:^10}|{mttr:^8.2f}|{failures:^8}|{risk_short_lived:^18}|{risk_long_lived:^18}|")


def display_application_info():
    """Exibe informações sobre as aplicações, seus servidores de alocação e usuários.
    Esta função mostra a cada passo da simulação onde cada aplicação está alocada
    e quais usuários estão acessando cada aplicação.
    """
    print("\n\n")
    print("==========================================================================")
    print("================= INFORMAÇÕES DE APLICAÇÕES E SERVIDORES =================")
    print("==========================================================================")
    
    print(f"{'Aplicação ID':^12}|{'Servidor ID':^12}|{'Usuário ID':^12}|{'Status':^10}")
    print("-" * 50)
    
    for application in Application.all():
        # Para cada aplicação, encontrar o servidor onde está alocada
        service = application.services[0] if application.services else None
        server_id = service.server.id if service and service.server else "N/A"
        
        # Encontrar os usuários que acessam esta aplicação
        users = application.users
        
        if users:
            # Se houver usuários, mostramos uma linha para cada usuário
            for user in users:
                status = "Online" if application.availability_status else "Offline"
                print(f"{application.id:^12}|{server_id:^12}|{user.id:^12}|{status:^10}")
        else:
            # Se não houver usuários, mostramos apenas a aplicação e o servidor
            status = "Online" if application.availability_status else "Offline"
            print(f"{application.id:^12}|{server_id:^12}|{'N/A':^12}|{status:^10}")


