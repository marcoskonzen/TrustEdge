# Importing EdgeSimPy components
from edge_sim_py import *

# Importing native Python modules/packages
from json import dumps

# Importing helper functions
from simulator.helper_functions import *

from simulator.extensions import *

# Importing logging modules
import math
from datetime import datetime

# Calculating reliability metrics

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
    
    # for failure_occurrence in server.failure_model.failure_history:
    #     # Só considera falhas que aconteceram durante a simulação efetiva (início >= current_step)
    #     if failure_occurrence["failure_starts_at"] >= current_step and failure_occurrence["becomes_available_at"] < current_step:
    #         # Calcula o tempo de falha até o step atual ou até o reparo, o que vier primeiro
    #         failure_start = max(failure_occurrence["failure_starts_at"], current_step)
    #         failure_end = min(failure_occurrence["becomes_available_at"], current_step)
    #         total_downtime += failure_end - failure_start
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
    # current_step = server.model.schedule.steps + 1
    
    # # Se ainda estamos no step 1 (inicialização), retorna 0
    # if current_step <= 1:
    #     return 0
    
    # # Simulação efetiva vai do step 2 até o step atual
    # simulation_start = 2
    # simulation_duration = current_step - simulation_start + 1
    
    # # O uptime é o tempo total da simulação efetiva menos o downtime
    # total_downtime = get_server_downtime_simulation(server=server)
    # total_uptime = simulation_duration - total_downtime
    
    # return max(0, total_uptime)  # Garantir que não seja negativo

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
        O step 1 (primeiro step) não é considerado pois é usado apenas para inicialização.
        As métricas de simulação começam a contar a partir do step 2.
    """
    # if not hasattr(user, "user_perceived_downtime_history"):
    #     return 0
        
    # if str(application_id) not in user.user_perceived_downtime_history:
    #     return 0

    # perceived_downtime = 0
  
    # for downtime in application.downtime_history:
    #     if downtime is True:
    #         perceived_downtime += 1

    
    # Se não há histórico suficiente (step 1 ou menos), retorna 0
    # if len(downtime_history) <= 1:
    #     return 0
        
    # Conta os casos onde o usuário percebeu downtime (True nos registros)
    # Pular o primeiro item do histórico (step 1 de inicialização)
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
    for edge_server in available_servers:
        if calculate_path_delay(origin_network_switch=user_switch, target_network_switch=edge_server.network_switch) <= delay_sla:
            edge_servers_that_dont_violate_delay_sla += 1

    if edge_servers_that_dont_violate_delay_sla == 0:
        app_delay_score = 0
    else:
        app_delay_score = 1 / ((edge_servers_that_dont_violate_delay_sla * delay_sla) ** (1 / 2))

    return app_delay_score

def get_server_trust_score(server):
    """Calcula um score de risco instantâneo para o servidor.
    
    O score é calculado multiplicando-se:
    1. Taxa de falhas (quanto maior, pior)
    2. Proporção do tempo desde o último reparo em relação ao MTBF
       (quanto maior essa proporção, maior o risco de uma falha iminente)
    
    Um servidor com menor score de risco é mais confiável porque:
    - Tem menor taxa de falhas historicamente
    - Ainda não se aproximou de seu MTBF desde o último reparo
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Score de risco (quanto menor, melhor - indica maior confiabilidade).
              Servidores que nunca falharam retornam 0 (máxima confiabilidade).
    """
    # Obter os valores dos parâmetros
    failure_rate = get_server_failure_rate(server)
    time_since_repair = get_time_since_last_repair(server)
    mtbf = get_server_mtbf(server)
    
    # Caso especial: servidor nunca falhou ou tem dados históricos insuficientes
    if failure_rate == 0 or mtbf == float("inf"):
        return 0
    
    # Caso especial: se time_since_repair for infinito, significa que não há registros 
    # de reparos concluídos antes do tempo atual, então usamos um valor padrão
    # if time_since_repair == float("inf"):
    #     # Consideramos que o servidor está em seu primeiro ciclo de vida
    #     # e usa um valor proporcional pequeno (10% do MTBF) para não superestimar o risco
    #     time_since_repair = 0.1 * mtbf

    if time_since_repair == 0:
        return float("inf")  # Risco máximo se o servidor está atualmente em falha  

    # Calcular a proporção do tempo desde o último reparo em relação ao MTBF
    proportion = time_since_repair / mtbf
    
    # Limitar a proporção a um máximo de 2.0 para evitar crescimento excessivo
    #proportion = min(proportion, 2.0)

    # Cálculo: multiplicar a taxa de falha pela proporção do tempo desde reparo/MTBF
    # Quanto menor o resultado, menor o risco de falha (mais confiável)
    risk_score = failure_rate * proportion
    
    return risk_score


def get_host_candidates(user: object, service: object) -> list:
    """Get list of host candidates for hosting services of a given user.
    Args:
        user (object): User object.
    Returns:
        host_candidates (list): List of host candidates.
    """
    
    app_delay = user.delays[str(service.application.id)] if user.delays[str(service.application.id)] is not None else 0

    host_candidates = []
    
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    for edge_server in available_servers:
        additional_delay = calculate_path_delay(
            origin_network_switch=user.base_station.network_switch, target_network_switch=edge_server.network_switch
        )
        overall_delay = app_delay + additional_delay
        sla_violations = 1 if overall_delay > user.delay_slas[str(service.application.id)] else 0

        # Gathering the edge server's trust score
        trust_score_edge_server = get_server_trust_score(edge_server)

        # Gathering the edge server's power consumption cost based on its CPU usage
        static_power_consumption = edge_server.power_model_parameters["static_power_percentage"]
        consumption_per_core = edge_server.power_model_parameters["max_power_consumption"] / edge_server.cpu
        power_consumption = consumption_per_core + static_power_consumption * (1 - sign(edge_server.cpu_demand))

        host_candidates.append(
            {
                "object": edge_server,
                "sla_violations": sla_violations,
                "trust_score": trust_score_edge_server,
                "power_consumption": power_consumption,
                "overall_delay": overall_delay,
            }
        )

    return host_candidates


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
        trust_score = get_server_trust_score(server)
        time_since_repair = get_time_since_last_repair(server)


        history_downtime = get_server_downtime_history(server)
        history_uptime = get_server_uptime_history(server)
        sim_uptime = get_server_uptime_simulation(server)
        sim_downtime = get_server_downtime_simulation(server)
        
        server_metrics[f"Server {server.id}"] = {
            "Risk Score": trust_score,
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
    
    Os servidores são ordenados por score de risco (crescente), 
    onde valores menores indicam servidores mais confiáveis.
    
    O score de risco é calculado como: taxa_falha * (tempo_desde_reparo/MTBF)
    Quanto mais próximo o servidor estiver de seu tempo médio entre falhas,
    maior será seu score de risco.
    
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

    # Ordenar por score de risco (crescente) - servidores mais confiáveis primeiro (menor score)
    servers = sorted(available_servers, key=lambda s: get_server_trust_score(s))
    
    # Cabeçalho da tabela
    print(f"{'Rank':^5}|{'ID':^5}|{'Status':^10}|{'Score Risco':^12}|{'Taxa Falha':^12}|{'T.Últ.Rep':^10}|{'MTBF':^10}|{'MTTR':^8}|{'Falhas':^8}|{'Conf. short_lived':^18}|{'Conf. long_lived':^18}|")
    print(f"{'':^5}|{'':^5}|{'':^10}|{'(F×T/MTBF)':^12}|{'':^12}|{'':^10}|{'':^10}|{'':^8}|{'':^8}|{'':^18}|{'':^18}|")
    print("-" * 125)

    for rank, server in enumerate(servers, 1):
        server_id = server.id
        server_status = getattr(server, 'status', 'N/A')
        failures = get_server_total_failures(server)
        mttr = get_server_mttr(server)
        mtbf = get_server_mtbf(server)
        risk_score = get_server_trust_score(server)
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
        
        # Formatação especial para risk score
        if risk_score == 0:
            risk_score_str = "Mínimo"
        else:
            risk_score_str = f"{risk_score:.4f}"

        print(f"{rank:^5}|{server_id:^5}|{server_status:^10}|{risk_score_str:^12}|{failure_rate:^12.6f}|{time_repair_str:^10}|{mtbf_str:^10}|{mttr:^8.2f}|{failures:^8}|{risk_short_lived:^18}|{risk_long_lived:^18}|")


def print_application_info():
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


def log_entities_state(parameters: dict = {}):
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


"""TRUST EDGE ORIGINAL ALGORITHM"""

def trust_edge_original(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge.
    
    Args:
        parameters (dict): Parâmetros da simulação.
    """

    
    
    

    #print_application_info()

    # Registrar o estado atual de todas as entidades para diagnóstico
    #print("[DEBUG] Chamando log_entities_state")
    #log_entities_state(parameters)

    # print("==========================================================================")
    # print(f"================= FIM DO STEP {current_step} ==========================")
    # print("==========================================================================")
    # print("\n\n")

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

