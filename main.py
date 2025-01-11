from datetime import datetime

TIME_DURATION_UNITS = (
    ('w', 60*60*24*7),
    ('d', 60*60*24),
    ('h', 60*60),
    ('m', 60),
    ('s', 1)
)
def toDateTime(timestamp):
    if not timestamp or timestamp == 0:
        return None
    if isinstance(timestamp, int):
        return datetime.fromtimestamp(timestamp)
    if isinstance(timestamp, str):
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f')
    raise ValueError("Unsupported timestamp format")

def human_time_duration(seconds):
    if seconds == 0:
        return 'inf'
    parts = []
    for unit, div in TIME_DURATION_UNITS:
        amount, seconds = divmod(int(seconds), div)
        if amount > 0:
            parts.append('{}{}{}'.format(amount, unit, "" ))
    return ' '.join(parts)

#def toDateTime(timestamp):
#    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f')

def format_timestamp(timestamp):
    dt = toDateTime(timestamp)
    return dt.strftime('%H:%M')

class Event:
    def __init__(self,eventType="",startTimestamp=0,endTimestamp=0):
        self.startTimestamp = startTimestamp
        self.endTimestamp = endTimestamp
        self.eventType = eventType

    def minutes(self):
        return (toDateTime(self.endTimestamp) - toDateTime(self.startTimestamp)).seconds / 60

class Night:
    def __init__(self):
        self.startSequence = 0
        self.endSequence = 0
        self.startTimestamp = 0
        self.endTimestamp = 0
        self.exposureTime = 0
        self.exposures = 0
        self.events = []

    def updateStartEnd(self, timestamp):
        if self.startTimestamp == 0:
            self.startTimestamp = timestamp
        self.endTimestamp = timestamp
   
    def getSequenceDuration(self):
        return (toDateTime(self.endSequence) - toDateTime(self.startSequence)).seconds 
    
    def getImagingDuration(self):
        return (toDateTime(self.endTimestamp) - toDateTime(self.startTimestamp)).seconds
    
    def getTotalUnsafeMinutes(self):
        total = 0
        for event in self.events:
            if event.eventType == "unsafe":
                total += event.minutes()
        return total
    
    def getTotalSafeMinutes(self):
        return (toDateTime(self.endTimestamp) - toDateTime(self.startTimestamp)).seconds / 60 - self.getTotalUnsafeMinutes()
        
        
class Observation:
    def __init__(self):
        self.date = ""
        self.name = ""
        self.filter = ""
        self.exposure = 0
        self.hfr = 0
        self.stars = 0
        self.drift = 0
    
    def __str__(self):
        return f"Date:{self.date} Obj:{self.name} Filter:{self.filter} Exp:{self.exposure} HFR:{self.hfr} Stars:{self.stars} Drift:{self.drift} "
    
class Object:    
    def __init__(self, name=""):
        self.observations = []
        self.name = name

    def add(self, observation):
        self.observations.append(observation)

    def getStartTimestamp(self):
        return str(self.observations[0].date)
    
    def getEndTimestamp(self):
        return str(self.observations[-1].date)

    def get_summary(self):
        total_exposure_time = sum(obs.exposure for obs in self.observations)
        average_hfr = sum(obs.hfr for obs in self.observations) / len(self.observations)
        average_drift = sum(obs.drift for obs in self.observations) / len(self.observations)
        number_of_observations = len(self.observations)

        exposure_time_by_filter = {}
        for observation in self.observations:
            filter = observation.filter
            exposure = observation.exposure

            if filter not in exposure_time_by_filter:
                exposure_time_by_filter[filter] = (0, 0)

            total_exposure, num_exposures = exposure_time_by_filter[filter]
            exposure_time_by_filter[filter] = (total_exposure + exposure, num_exposures + 1)

        print("\n" )
        print(f"Object Summary for {self.name}:")        
        #for filter, exposure in exposure_time_by_filter.items():
        #    print(f"  {filter}: {exposure} seconds ({exposure/3600} hours)")
        for filter, (total_exposure, num_exposures) in exposure_time_by_filter.items():
            print(f"  Filter {filter}: {num_exposures} exposures, {human_time_duration(total_exposure)} ")

        # if more then one filter
        if len(exposure_time_by_filter) > 1:
            print(f"Total {number_of_observations} exposures,  Exposure Time: {human_time_duration(total_exposure_time)}")
        print(f"Average HFR: {average_hfr} asec" )
        print(f"Average Drift: {average_drift}")
        
        '''
        print("**** DETAILS ****\n")

        #print details
        for obs in self.observations:
            print(obs)
        '''
 
def log_parser(log_file):
    f = open(log_file, "r")
    lines = f.readlines()

    objects = {}
    obj = Observation()
    night = Night()
    event = Event()

    messageOld = ""
    

    for line in lines:
        # if line starts with "---" then ignore it
        if line.startswith("---"):
            continue

        parts = line.split("|")
        obj.date = parts[0]
        fields = ["", "", "", "", ""]
        for i in range(1, 6):
            try:
                fields[i-1] = parts[i]
            except IndexError:
                pass

        level, source, member, line, message = fields

        if member == "StartSequence":
            if message.startswith("Advanced Sequence finished"):
                if not messageOld.startswith("Sequence run was cancelled"):                        
                    night.endSequence = obj.date
                    night.events.append(Event("Sequence finished", 0, night.endSequence))

        if member == "StartSequence":
            if message.startswith("Advanced Sequence starting"):                
                if not messageOld.startswith("InterruptWhen: Sequence longer running"):                    
                    night.startSequence = obj.date
                    night.events.append(Event("Sequence starting", night.startSequence, 0))

        if member == "UpdateMonitorValues":
            if message.startswith("SafetyMonitorInfo state changed to Unsafe"):
                event = Event("unsafe")
                event.startTimestamp = obj.date
                obj = Observation()
        
        if member == "UpdateMonitorValues":
            if message.startswith("SafetyMonitorInfo state changed to Safe"):
                
                event.endTimestamp = obj.date
                night.events.append(event)

        if member == "Capture":
            obj.exposure = int(message.split(";")[0].split(":")[1].replace("s", ""))
            
            night.updateStartEnd(obj.date)

        if member == "Detect":            
            obj.hfr   = float(message.split(",")[0].split(":")[1])
            obj.stars = int(message.split(",")[2].split(" ")[3])            

        if member == "PlatesolvingImageFollower_PropertyChanged":
            obj.drift = float(message.split(",")[0].split(":")[1].split('/')[0])

        if member == "SaveToDisk":
            if (message.__contains__("AppData\\Local\\NINA\\PlateSolver")):
                continue
            obj.filter = message.split("\\")[-2]            
            obj.name = message.split("\\")[-4]
            night.exposureTime += obj.exposure
            night.exposures += 1
           
            

            

            if obj.name not in objects:                
                objects[obj.name] = Object(obj.name)
            else:                
                objects[obj.name].add(obj)
            obj = Observation()

        messageOld = message
        
           
    f.close()


    print ("Summary:")

    print (f"Sequence started at {night.startSequence} and ended at {night.endSequence} ({human_time_duration(night.getSequenceDuration())})")
    print (f"Imaged from {night.startTimestamp} until {night.endTimestamp} ({human_time_duration(night.getImagingDuration())})")    
    print (f"Total exposures: {night.exposures}")
    print (f"Exposure time: {human_time_duration( night.exposureTime)}")
    print (f"Safe duration: {human_time_duration(night.getTotalSafeMinutes() * 60)}")
    print (f"Unsafe duration: {human_time_duration(night.getTotalUnsafeMinutes() * 60)}")

    # add observations to events
    for obj in objects.values():                               
        start_timestamp = obj.getStartTimestamp()
        end_timestamp = obj.getEndTimestamp()
        night.events.append(Event(obj.name, start_timestamp, end_timestamp))
        

    night.events.sort(key=lambda x: toDateTime(x.startTimestamp) or datetime.max)

    print (f"Events: {len(night.events)}")
    for event in night.events:
        try:
            start =  format_timestamp(event.startTimestamp)
        except:
            start = ""

        try:
            end = format_timestamp(event.endTimestamp)
        except:
            end = ""    
        
        try:
            duration = human_time_duration(event.minutes() * 60)
        except:
            duration = ""
        
        print(f" {start}-{end}  \t{event.eventType} ({duration})")

    for obj in objects.values():
        obj.get_summary()


def main():
    log_parser("example.log")

if __name__ == '__main__':
    main()