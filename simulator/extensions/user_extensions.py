# Importing EdgeSimPy components
from edge_sim_py.components.base_station import BaseStation

def user_step(self):
    """Method that executes the events involving the object at each time step."""
    # Updating user access
    current_step = self.model.schedule.steps + 1
    
    for app in self.applications:
        last_access = self.access_patterns[str(app.id)].history[-1]

        # Updating user access waiting and access times. Waiting time represents the period in which the user is waiting for
        # his application to be provisioned. Access time represents the period in which the user is successfully accessing
        # his application, meaning his application is available. We assume that an application is only available when all its
        # services are available.
        if self.making_requests[str(app.id)][str(current_step)] == True:
            if len([s for s in app.services if s._available]) == len(app.services):
                last_access["access_time"] += 1
            else:
                last_access["waiting_time"] += 1

        # Updating user's making requests attribute for the next time step
        if current_step + 1 >= last_access["start"] and current_step + 1 <= last_access["end"]:
            self.making_requests[str(app.id)][str(current_step + 1)] = True
        else:
            self.making_requests[str(app.id)][str(current_step + 1)] = False

        # Creating new access request if needed
        if current_step + 1 == last_access["next_access"]:
            self.making_requests[str(app.id)][str(current_step + 1)] = True
            self.access_patterns[str(app.id)].get_next_access(start=current_step + 1)

    # Re-executing user's mobility model in case no future mobility track is known by the simulator
    if len(self.coordinates_trace) <= current_step:
        self.mobility_model(self)

    # Updating user's location
    if self.coordinates != self.coordinates_trace[current_step]:
        self.coordinates = self.coordinates_trace[current_step]

        # Connecting the user to the closest base station
        self.base_station = BaseStation.find_by(attribute_name="coordinates", attribute_value=self.coordinates)

        for application in self.applications:
            # Only updates the routing path of apps available (i.e., whose services are available)
            services_available = len([s for s in application.services if s._available])
            #print(f"Service available: {services_available}")
            if services_available == len(application.services):
                # Recomputing user communication paths
                self.set_communication_path(app=application)
            else:
                self.communication_paths[str(application.id)] = []
                #self._compute_delay(app=application)
