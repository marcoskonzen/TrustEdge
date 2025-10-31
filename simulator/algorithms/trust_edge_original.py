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


"""TRUST EDGE ORIGINAL ALGORITHM"""

def trust_edge_original(parameters: dict = {}):
    """Algoritmo que implementa um placement estático, sem alterar o posicionamento das aplicações.
    
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