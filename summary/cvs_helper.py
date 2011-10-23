from django.http import HttpResponse, HttpResponseRedirect
from time import time,mktime,strftime
import datetime_helper
from datetime import datetime, timedelta

def linegraph_bucket(data,bucket_size,title):
	result={}
	result['name'] = title
	result['type'] = "spline"
	output=[]

	try:	
		start_time = datetime_helper.datetime_format_to_unixtime(data[0].eventstamp)
		end_time = start_time + bucket_size

		bucket = []

		for measure in data:
			time = datetime_helper.datetime_format_to_unixtime(measure.eventstamp)

			if time < end_time:
				bucket.append(int(measure.average))
			else:
			   	mid_time = (start_time + end_time)/2
			   	n = len(bucket)
				if n!=0:
			   		mean = sum(bucket) / n
					temp=[]
					temp.append(datetime.fromtimestamp(mid_time))
					temp.append(int(mean))
					output.append(temp)
					
					
			   	bucket = []
				
			   	while(time>end_time):
			
			   		start_time = end_time+1;
			   		end_time = start_time+bucket_size
								  
			   		bucket.append(int(measure.average))

		n = len(bucket)
		if n!=0:
			mean = sum(bucket) / n
			temp=[]
			temp.append(datetime.fromtimestamp(mid_time))
			temp.append(int(mean))
			output.append(temp)

		result['data']=output
	except:
		 return result

	return result

def linegraph_normal(data,title):
    result={}
    result['name'] = title
    result['type'] = "spline"
    output= []

    for measure in data:

	if(measure.average <= 0):
		continue
	temp=[]
	temp.append(datetime.fromtimestamp(mktime(measure.eventstamp.timetuple())))
	temp.append(int(measure.average))
	output.append(temp)

    result['data'] = output
    return result


