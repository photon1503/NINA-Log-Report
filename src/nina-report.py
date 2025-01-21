from datetime import datetime
from datetime import timedelta
import json
import os
import argparse

from src.pushover import PushoverClient


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

class Report:
    def __init__(self):
        self.lines = []

    def addString(self, string):
        # add string to last line
        self.lines[-1] += string

    def addLine(self, line=None):
        if line is None:
            self.lines.append("")
        else:
            self.lines.append(line)

    def getLines(self):
        return "\n".join(self.lines)
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
        self.errors = 0

    def addError(self):
        self.errors += 1


      

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

    def get_summary(self, report):
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

        report.addLine()
        report.addLine(f"Object Summary for {self.name}:")        
        #for filter, exposure in exposure_time_by_filter.items():
        #    print(f"  {filter}: {exposure} seconds ({exposure/3600} hours)")
        for filter, (total_exposure, num_exposures) in exposure_time_by_filter.items():
            report.addLine(f"  Filter {filter}: {num_exposures} exposures, {human_time_duration(total_exposure)} ")

        # if more then one filter
        if len(exposure_time_by_filter) > 1:
            report.addLine(f"Total {number_of_observations} exposures,  Exposure Time: {human_time_duration(total_exposure_time)}")
        report.addLine(f"Average HFR: {average_hfr:.2f} asec" )
        report.addLine(f"Average Drift: {average_drift:.2f} asec/s" )
        

def parse_log_file(log_file, pattern):
    f = open(log_file, "r")
    lines = f.readlines()

    messageOld = ""
    exp = Exposure()   
    event = Event()
    startEndSequence=0
    startBeginSequence=0
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
    
        if level == "ERROR":
            night.addError()

        # SequenceItem.cs|Run|208|Starting Category: * Instruction Set *, Container: NINA.Sequencer.Container.EndAreaContainer   
        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.EndAreaContainer") and message.startswith("Starting"):
                startEndSequence = exp.date
            if message.__contains__("NINA.Sequencer.Container.EndAreaContainer") and message.startswith("Finishing"):
                night.endSequence = exp.date
                night.events.append(Event("End sequence", startEndSequence, night.endSequence))

        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.TargetAreaContainer") and message.startswith("Finishing"):
                night.endSequence = exp.date
                night.events.append(Event("Finished Target Scheduler", night.endSequence, night.endSequence))

        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.TargetAreaContainer") and message.startswith("Starting"):
                night.endSequence = exp.date
                night.events.append(Event("Started Target Scheduler", night.endSequence, night.endSequence))

        if member == "Start":
            if message.startswith("Sequence run was cancelled"):
                night.events.append(Event("Sequence cancelled", exp.date, exp.date))

        if member == "Run":
            if message.__contains__("NINA.Sequencer.Container.StartAreaContainer") and message.startswith("Starting"):
                startBeginSequence = exp.date
            if message.__contains__("NINA.Sequencer.Container.StartAreaContainer") and message.startswith("Finishing"):
                night.startSequence = exp.date
                night.events.append(Event("Start sequence", startBeginSequence, night.startSequence))
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

 
            if pattern == "AMOS":
                try:
                    exp.name = message.split("\\")[-1].split("_")[7].replace(" ", "")
                except:
                    exp.name = "Unknown"
            if pattern == "skyimages":
                try:
                    exp.name = message.split("\\")[-4]
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
 
def log_parser(path, pattern):
    import glob

    #path = r"C:/git/NINA Report/AMOS"
    log_files = glob.glob(os.path.join(path, "*.log"))

    log_files.sort()
    for log_file in log_files:
        # remove path
        baseName = os.path.basename(log_file)
        print(f"Processing {log_file}")
        if baseName.startswith("20"):
            parse_log_file(log_file, pattern)


    

def generate_night_summary(night, report, silent=False):
    if night.startTimestamp == 0:
        if silent == False:
            report.addLine(f"No activities for {night.date}" )
            return

    nighttime = datetime.strptime(night.startTimestamp,'%Y-%m-%dT%H:%M:%S.%f').strftime('%Y-%m-%d')
    
    report.addLine(f"Summary for {night.date}" )

    report.addLine (f"Total images: \t{night.exposures}")
    report.addLine (f"Exposure time: \t{human_time_duration( night.exposureTime)}")
    report.addLine (f"Safe duration: \t{human_time_duration(night.getTotalSafeMinutes() * 60)}")
    if night.getTotalUnsafeMinutes() > 0:
        report.addLine (f"Unsafe dur.: \t{human_time_duration(night.getTotalUnsafeMinutes() * 60)}")

    if night.errors > 0:
        report.addLine (f"Errors: \t\t{night.errors}")

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
    report.addLine()
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
        

        if start == end:
             report.addLine(f" {start} {event.eventType}" )
     
        else:
            report.addLine(f" {start}-{end} {event.eventType}" )
            if duration != "":
                report.addString(f" ({duration})")


    for obj in night.objects.values():
        obj.get_summary(report)


def main():
    parser = argparse.ArgumentParser("nina_report")
    parser.add_argument("-n", "--night", help="0=last night, 1=the night before etc.", type=int, default=0)
    parser.add_argument("-P", "--pushover", help="Send report to pushover", action="store_true", default=False)
    parser.add_argument("-p", "--path", help="Path to NINA log files", default="%LOCALAPPDATA%/NINA/Logs")
    parser.add_argument("-o", "--pattern", help="Pattern to use for parsing. Currently supported values are skyimages and AMOS", default="AMOS")
    parser.add_argument("-s", "--silent", help="Disable message without content", action="store_true",default=False)
    args = parser.parse_args()
   
    with open('secrets.json') as secrets_file:
        secrets = json.load(secrets_file)
    pushover = PushoverClient(secrets.get("PUSHOVER_APIKEY"), secrets.get("PUSHOVER_USERKEY"))

    log_parser(args.path, args.pattern)

    # by default, print only last night
    if len(nights.nights) == 0:
        print("No data found")
        return
    
    n = -(args.night + 1)
    print (f"Processing night {n}")
    last_night = nights.nights[n]
    report=Report()
    generate_night_summary(last_night, report, args.silent)
    if last_night.startTimestamp == 0 and args.silent:
        return
    
    if args.pushover:
        pushover.send_message(report.getLines(), f"NINA Report for {last_night.date}")
    else:
        print(report.getLines())

if __name__ == '__main__':
    main()