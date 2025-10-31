def application_step(self):
    """Method that executes the events involving the object at each time step."""

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
    all_downtime = []
    
    for user in self.users:
        if (hasattr(user, "user_perceived_downtime_history") and 
            str(self.id) in user.user_perceived_downtime_history):
            # Adicionar histórico deste usuário
            all_downtime.extend(user.user_perceived_downtime_history[str(self.id)])
    
    return all_downtime