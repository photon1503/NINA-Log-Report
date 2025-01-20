from datetime import datetime
from datetime import timedelta
import os


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

class Nights:
    def __init__(self):
        self.nights = []

    def add(self, night):
        self.nights.append(night)

    def addNight(self, date):
        night = Night()
        night.date = date
        self.nights.append(night)
        return night    
    
    def getNight(self, date):
        for night in self.nights:                        
            if date.split("T")[1] < "12:00:00":
                if night.date == (datetime.strptime(date.split("T")[0], '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d'):
                    return night
            if night.date == date.split("T")[0]:
                return night
            
        return self.addNight(date.split("T")[0])

nights = Nights()
class Night:
    def __init__(self):
        self.date = None
        self.startSequence = 0
        self.endSequence = 0
        self.startTimestamp = 0
        self.endTimestamp = 0
        self.exposureTime = 0
        self.exposures = 0
        self.events = []
        self.objects = {}


      

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
        
        
class Exposure:
    def __init__(self):
        self.date = ""
        self.name = ""
        self.filter = ""
        self.exposure = 0
        self.hfr = 0
        self.stars = 0
        self.drift = 0
    
    
class Target:    
    def __init__(self, name=""):
        self.observations = []
        self.name = name

    def add(self, observation):
        self.observations.append(observation)

    def getStartTimestamp(self):
        if len(self.observations) == 0:
            return None
        return str(self.observations[0].date)
    
    def getEndTimestamp(self):
        if len(self.observations) == 0:
            return None
        return str(self.observations[-1].date)

    def get_summary(self):
        total_exposure_time = sum(obs.exposure for obs in self.observations)
        if len(self.observations) != 0:
            average_hfr = sum(obs.hfr for obs in self.observations) / len(self.observations)
        else:
            average_hfr = 0
        if len(self.observations) != 0:
            average_drift = sum(obs.drift for obs in self.observations) / len(self.observations)
        else:
            average_drift = 0
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
        print(f"Average HFR: {average_hfr:.2f} asec" )
        print(f"Average Drift: {average_drift:.2f} asec/s" )
        

def parse_log_file(log_file):
    f = open(log_file, "r")
    lines = f.readlines()

    messageOld = ""
    exp = Exposure()   
    event = Event()
    
    for line in lines:
        # if line starts with "---" then ignore it
        if line.startswith("---"):
            continue

        if line.startswith("DATE|"):
            continue

        if not line.startswith("20"):
            continue

        parts = line.split("|")
        exp.date = parts[0]
        fields = ["", "", "", "", ""]
        for i in range(1, 6):
            try:
                fields[i-1] = parts[i]
            except IndexError:
                pass

        level, source, member, line, message = fields     

        night = nights.getNight(exp.date)  
           
        # SequenceItem.cs|Run|208|Starting Category: * Instruction Set *, Container: NINA.Sequencer.Container.EndAreaContainer   
        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.EndAreaContainer") and message.startswith("Finishing"):
                night.endSequence = exp.date
                night.events.append(Event("Finished End sequence", night.endSequence, night.endSequence))

        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.TargetAreaContainer") and message.startswith("Finishing"):
                night.endSequence = exp.date
                night.events.append(Event("Finished Target Scheduler", night.endSequence, night.endSequence))

        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.TargetAreaContainer") and message.startswith("Starting"):
                night.endSequence = exp.date
                night.events.append(Event("Started Target Scheduler", night.endSequence, night.endSequence))

        if line == "Run":
              if message.__contains__("NINA.Sequencer.Container.StartAreaContainer") and message.startswith("Finishing"):
                night.startSequence = exp.date
                night.events.append(Event("Finished start sequence", night.startSequence, night.startSequence))
                # set next day to obj.date + 1 at 12:00 
                # add 1 day to obj.date
                nextDay = datetime.strptime(exp.date.split("T")[0], '%Y-%m-%d') + timedelta(days=1)
                nextDay = nextDay.strftime('%Y-%m-%d') + "T12:00:00.0000"
                
        if member == "UpdateMonitorValues":
            if message.startswith("SafetyMonitorInfo state changed to Unsafe"):
                event = Event("unsafe")
                event.startTimestamp = exp.date
                exp = Exposure()
        
        if member == "UpdateMonitorValues":
            if message.startswith("SafetyMonitorInfo state changed to Safe"):
                
                event.endTimestamp = exp.date
                night.events.append(event)

        if member == "Capture":
            try:
                exp.exposure = float(message.split(";")[0].split(":")[1].replace("s", ""))
                
                night.updateStartEnd(exp.date)
            except:
                pass

        if member == "Closing":
            if message.startswith("Application shutting down"):
                night.endTimestamp = exp.date
                night.events.append(Event("NINA stopped", night.endTimestamp, night.endTimestamp))

        if member == "CheckASCOMPlatformVersion":
            night.events.append(Event("NINA started", exp.date, exp.date))
        if member == "Detect":            
            exp.hfr   = float(message.split(",")[0].split(":")[1])
            exp.stars = int(message.split(",")[2].split(" ")[3])            

        if member == "PlatesolvingImageFollower_PropertyChanged":
            exp.drift = float(message.split(",")[0].split(":")[1].split('/')[0])

        if member == "SaveToDisk":
            if (message.__contains__("AppData\\Local\\NINA\\PlateSolver")):
                continue
            exp.filter = message.split("\\")[-2]            

            #obj.name = message.split("\\")[-4]
            # C:\Users\AMOS\Documents\N.I.N.A\2025-01-03\LIGHT\2025-01-03_19-45-31_Lum_-15.00_300.00s_0000_20.30_NGC 1977_2.77_0.53__.fits
            # NGC 977 is name
            try:
                exp.name = message.split("\\")[-1].split("_")[7].replace(" ", "")
            except:
                exp.name = "Unknown"
            night.exposureTime += exp.exposure
            night.exposures += 1

            if exp.name not in night.objects:                
                night.objects[exp.name] = Target(exp.name)
            else:                
                night.objects[exp.name].add(exp)
            exp = Exposure()

        messageOld = message
        
           
    f.close()
 
def log_parser(path):
    import glob

    #path = r"C:/git/NINA Report/AMOS"
    log_files = glob.glob(os.path.join(path, "*.log"))

    log_files.sort()
    for log_file in log_files:
        # remove path
        baseName = os.path.basename(log_file)
        print(f"Processing {log_file}")
        if baseName.startswith("20"):
            parse_log_file(log_file)


    

def generate_night_summary(night):
    if night.startTimestamp == 0:
        print (f"No activities for {night.date}" )
        return

    nighttime = datetime.strptime(night.startTimestamp,'%Y-%m-%dT%H:%M:%S.%f').strftime('%Y-%m-%d')
    
    print (f"Summary for {night.date}" )

    print (f"Total images: \t{night.exposures}")
    print (f"Exposure time: \t{human_time_duration( night.exposureTime)}")
    print (f"Safe duration: \t{human_time_duration(night.getTotalSafeMinutes() * 60)}")
    if night.getTotalUnsafeMinutes() > 0:
        print (f"Unsafe dur.: \t{human_time_duration(night.getTotalUnsafeMinutes() * 60)}")

    # add observations to events
    for obj in night.objects.values():                               
        start_timestamp = obj.getStartTimestamp()
        end_timestamp = obj.getEndTimestamp()
        night.events.append(Event(obj.name, start_timestamp, end_timestamp))
        

    

    night.events.sort(key=lambda x: toDateTime(x.startTimestamp) or datetime.max)




    # Combine consecutive "unsafe" events
    combined_events = []
    previous_event = None

    for event in night.events:
        if previous_event and event.eventType == "unsafe" and previous_event.eventType == "unsafe":
            # Combine events if they are consecutive
            previous_event.endTimestamp = event.endTimestamp
            #previous_event.eventType = "unsafe (with gaps)"
        else:
            if previous_event:
                combined_events.append(previous_event)
            previous_event = event

    if previous_event:
        combined_events.append(previous_event)

    night.events = combined_events

    #print (f"Events: {len(night.events)}")
    print()
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
        
        if start == "":
            print (f"     ", end="")

        if start == end:
             print(f" {start}  \t{event.eventType}", end="" )
             print()
        else:
            print(f" {start}-{end}  \t{event.eventType}", end="" )
            if duration != "":
                print(f" ({duration})", end="")
            print()

    for obj in night.objects.values():
        obj.get_summary()


def main():
    path = "AMOS"
    log_parser(path)

    # by default, print only last night
    if len(nights.nights) == 0:
        print("No data found")
        return
    
    #last_night = nights.nights[-1]
    #generate_night_summary(last_night)

    for night in nights.nights:
        generate_night_summary(night)

if __name__ == '__main__':
    main()