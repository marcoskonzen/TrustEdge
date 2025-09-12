def application_step(self):
    """Method that executes the events involving the object at each time step."""
    
    # Updating the current perceived downtime of all users that access the application
    # for user in self.users:
    #     if not hasattr(user, "user_perceived_downtime_history"):
    #         user.user_perceived_downtime_history = {f"{self.id}": []}

    #     if user.making_requests[str(self.id)][str(self.model.schedule.steps + 1)]:
    #         user.user_perceived_downtime_history[f"{self.id}"].append(not self.availability_status)

    

@property
def availability_status(self):
    for service in self.services:
        if service._available is False:
            return False
    return True

@property
def availability_history(self):
    """Returns the history of the application's availability."""
    if not hasattr(self, "_availability_history"):
        self._availability_history = []

    current_step = self.model.schedule.steps
    if len(self._availability_history) <= current_step:
        self._availability_history.append(self.availability_status)
    
    return self._availability_history

@property
def downtime_history(self):
    # Updating and return the history perceived downtime of all users that access the application
    for user in self.users:
        if not hasattr(user, "user_perceived_downtime_history"):
            user.user_perceived_downtime_history = {f"{self.id}": []}

        if user.making_requests[str(self.id)][str(self.model.schedule.steps + 1)]:
            user.user_perceived_downtime_history[f"{self.id}"].append(not self.availability_status)

    return user.user_perceived_downtime_history[f"{self.id}"]