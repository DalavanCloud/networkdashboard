from django.http import HttpResponse, HttpResponseRedirect
import urllib2, urllib, json
from django.shortcuts import render_to_response
from networkdashboard.summary.models import *
import random
from datetime import datetime, timedelta
from time import time,mktime,strftime
import hashlib,httplib,urllib2
import cvs_helper,datetime_helper,geoip_helper, views_helper
import ast

# searches the provided queryset for deviceids which are not already in devicedetails. If the deviceid
# is missing, a new devicedetails record is created:
def add_new_devices(devices):
	all_details = Devicedetails.objects.all()
	for d in devices:
		# if no devicedetails record with this device id exists:
		if len(all_details.filter(deviceid=d['deviceid']))==0:
			# generate hashkey:
			hash = hashlib.md5()
			hash.update(d['deviceid'])
			hash = hash.hexdigest()
			# create new devicedetails record:
			new_details = Devicedetails(deviceid = d['deviceid'], eventstamp = datetime.now(), hashkey = hash)
			new_details.save()
	return

# appends new bitrate measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing.
def update_bitrate(device):
	chosen_limit = 100000000
	most_recent = []
	# get all cached data:
	cache_down = JsonCache.objects.filter(deviceid=device, datatype = "bitrate_down")
	cache_up = JsonCache.objects.filter(deviceid=device, datatype = "bitrate_up")
	# both caches already contain cached data:
	if (len(cache_down)!=0 and len(cache_up)!=0):
		all_device_details= MBitrate.objects.filter(average__lte=chosen_limit,deviceid=device)
		# no measurements for this device:
		if len(all_device_details)==0:
			return
		most_recent_measure = all_device_details.latest('eventstamp').eventstamp
		most_recent_cached = cache_down[0].eventstamp
		# cache is up to date
		if most_recent_measure<=most_recent_cached:
			return
		download_data = json.loads(cache_down[0].data)
		upload_data = json.loads(cache_up[0].data)
		# split into the seperate series, multi-threaded and single-threaded:
		download_multi = download_data[0]
		download_single = download_data[1]
		upload_multi = upload_data[0]
		upload_single = upload_data[1]
		# retrieve all uncached measurements:
		all_device_details= all_device_details.filter(eventstamp__gt=most_recent_cached)
		# if there are no uncached measurements:
		if len(all_device_details)==0:
			return
		downloads = all_device_details.filter(direction='dw')
		uploads = all_device_details.filter(direction='up')
		downloads_netperf_3 = downloads.filter(toolid='NETPERF_3').order_by('eventstamp')
		downloads_other = downloads.exclude(toolid='NETPERF_3').order_by('eventstamp')
		uploads_netperf_3 = uploads.filter(toolid='NETPERF_3').order_by('eventstamp')
		uploads_other = uploads.exclude(toolid='NETPERF_3').order_by('eventstamp')
		download_data[0]['data'].extend(cvs_helper.linegraph_normal(downloads_netperf_3,"Multi-threaded TCP",1000,18000,1,1)['data'])
		download_data[1]['data'].extend(cvs_helper.linegraph_normal(downloads_other,"Single-threaded TCP",1000,18000,0,1)['data'])
		upload_data[0]['data'].extend(cvs_helper.linegraph_normal(uploads_netperf_3,"Multi-threaded TCP",1000,18000,1,2)['data'])
		upload_data[1]['data'].extend(cvs_helper.linegraph_normal(uploads_other,"Single-threaded TCP",1000,18000,0,2)['data'])
		cache_down[0].data=json.dumps(download_data)
		cache_down[0].eventstamp = most_recent_measure
		cache_up[0].data= json.dumps(upload_data)
		cache_up[0].eventstamp = most_recent_measure
		cache_down[0].save()
		cache_up[0].save()
		return
	# 1 or both caches are empty:
	else:
		# check whether caches are empty or not. If only 1 cache is empty, trying to append to the data
		# portion of the non-empty cache would corrupt the cache. These are booleans which evaluate to true
		# in the event that the respective cache is indeed empty:
		cache_check_down = len(JsonCache.objects.filter(deviceid=device, datatype = "bitrate_down"))==0
		cache_check_up = len(JsonCache.objects.filter(deviceid=device, datatype = "bitrate_up"))==0
		all_device_details= MBitrate.objects.filter(average__lte=chosen_limit,deviceid=device)
		# no measurements exist at all:
		if len(all_device_details)==0:
			return
		most_recent_measure = all_device_details.latest('eventstamp').eventstamp
		downloads = all_device_details.filter(direction='dw')
		uploads = all_device_details.filter(direction='up')
		downloads_netperf_3 = downloads.filter(toolid='NETPERF_3').order_by('eventstamp')
		downloads_other = downloads.exclude(toolid='NETPERF_3').order_by('eventstamp')
		uploads_netperf_3 = uploads.filter(toolid='NETPERF_3').order_by('eventstamp')
		uploads_other = uploads.exclude(toolid='NETPERF_3').order_by('eventstamp')
		download_data = []
		upload_data = []
		download_data.append(cvs_helper.linegraph_normal(downloads_netperf_3,"Multi-threaded TCP",1000,18000,1,1))
		download_data.append(cvs_helper.linegraph_normal(downloads_other,"Single-threaded TCP",1000,18000,0,1))
		upload_data.append(cvs_helper.linegraph_normal(uploads_netperf_3,"Multi-threaded TCP",1000,18000,1,2))
		upload_data.append(cvs_helper.linegraph_normal(uploads_other,"Single-threaded TCP",1000,18000,0,2))
		if (cache_check_down):
			cache_down_new = JsonCache(deviceid = device, data = json.dumps(download_data), datatype = 'bitrate_down', eventstamp = most_recent_measure)
			cache_down_new.save()	
		if (cache_check_up):
			cache_up_new = JsonCache(deviceid = device, data = json.dumps(upload_data), datatype = 'bitrate_up', eventstamp = most_recent_measure)
			cache_up_new.save()
		return

# appends new rtt measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing. 		
def update_rtt(device):
	rtt_data=[]
	series_id=3
	priority=0
	cache = JsonCache.objects.filter(deviceid=device, datatype = "rtt")
	# cache contains cached data:
	if len(cache)!=0:
		full_details = MRtt.objects.filter(deviceid=device,average__lte=3000)
		if len(full_details)==0:
			return
		most_recent_cached = cache.latest('eventstamp').eventstamp
		most_recent_uncached = full_details.latest('eventstamp').eventstamp
		if (most_recent_uncached<=most_recent_cached):
			return
		rtt_data = json.loads(cache[0].data)
		# retrieve all uncached measurements:
		distinct_ips = full_details.values('dstip').distinct()
		full_details = full_details.filter(eventstamp__gt=most_recent_cached).order_by('eventstamp')
		location = ''
		dst_ip = ''
		for ip in distinct_ips:
			dst_ip = ip['dstip']
			try:
				ip_lookup = IpResolver.objects.filter(ip=dst_ip)
				# not an active measurement server:
				if len(ip_lookup)==0:
					continue
				else:
					location = ip_lookup[0].location
			except:
				continue
			device_details = full_details.filter(dstip = ip['dstip'])
			if len(device_details)==0:
				continue
			if(location=="Georgia Tech"):
				priority=1
			else:
				priority=0
			#find the correct series in the cache data to append to:
			for index in range(len(rtt_data)):
				if rtt_data[index]['name']==location:
					rtt_data[index]['data'].extend(cvs_helper.linegraph_normal(device_details,location,1,1,priority,series_id)['data'])
					break
				# new series:
				if (index==(len(rtt_data)-1)):
					rtt_data.append(cvs_helper.linegraph_normal(device_details,location,1,1,priority,series_id))
		cache[0].data = json.dumps(rtt_data)
		cache[0].eventstamp = most_recent_uncached
		cache[0].save()
		return
	# cache is empty:
	else:
		full_details = MRtt.objects.filter(deviceid=device,average__lte=3000)
		if len(full_details)==0:
			return
		most_recent = full_details.latest('eventstamp').eventstamp
		distinct_ips = full_details.values('dstip').distinct()
		# must wait until after distinct query before ordering original queryset:
		full_details = full_details.order_by('eventstamp')
		for ip in distinct_ips:
			try:
				ip_lookup = IpResolver.objects.filter(ip=ip['dstip'])[0]
				dst_ip = ip_lookup.ip
				location = ip_lookup.location
			except:
				continue
			device_details = full_details.filter(dstip = ip['dstip'])		
			if len(device_details)==0:
				continue
			if(location=="Georgia Tech"):
				priority=1
			else:
				priority=0
			rtt_data.append(cvs_helper.linegraph_normal(device_details,location,1,1,priority,series_id))
		cache_new = JsonCache(deviceid = device, data = json.dumps(rtt_data), datatype = 'rtt', eventstamp = most_recent)
		cache_new.save()
		return

# appends new lmrtt measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing.
def update_lmrtt(device):
	lmrtt_data=[]
	series_id=4
	lmrtt_cache = JsonCache.objects.filter(deviceid=device, datatype='lmrtt')
	if len(lmrtt_cache)!=0:
		all_records = MLmrtt.objects.filter(deviceid=device,average__lte=3000)
		if (len(all_records)==0):
			return
		latest_record = all_records.latest('eventstamp')
		# cache is up to date:
		if latest_record.eventstamp<=lmrtt_cache[0].eventstamp:
			return
		uncached_measurements = all_records.filter(eventstamp__gt=lmrtt_cache[0].eventstamp).order_by('eventstamp')
		lmrtt_data = json.loads(lmrtt_cache[0].data)
		lmrtt_data[0]['data'].extend(cvs_helper.linegraph_normal(uncached_measurements,'Last mile latency',1,1,1,series_id)['data'])
		lmrtt_cache[0].data = json.dumps(lmrtt_data)
		lmrtt_cache[0].eventstamp = latest_record.eventstamp
		lmrtt_cache[0].save()
		return
	else:
		all_measurements = MLmrtt.objects.filter(deviceid=device,average__lte=3000)
		# no measurements for this device
		if len(all_measurements)==0:
			return
		latest_measurement = all_measurements.latest('eventstamp').eventstamp
		all_measurements = all_measurements.order_by('eventstamp')
		lmrtt_data.append(cvs_helper.linegraph_normal(all_measurements,'Last mile latency',1,1,1,series_id))
		new_cache = JsonCache(deviceid = device, data = json.dumps(lmrtt_data), datatype = 'lmrtt', eventstamp = latest_measurement)
		new_cache.save()
		return

# appends new capacity measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing.		
def update_capacity(device):
	series_id=5
	# series data for capacity, in json format:
	capacity_data = []
	# retrieve cached data:
	capacity_cache = JsonCache.objects.filter(deviceid=device,datatype='capacity')
	# cacehe not empty:
	if len(capacity_cache)!=0:
		all_measurements = MCapacity.objects.filter(deviceid=device)
		# no measurements:
		if len(all_measurements)==0:
			return
		most_recent_cached = capacity_cache.latest('eventstamp').eventstamp
		most_recent_uncached = all_measurements.latest('eventstamp').eventstamp
		if most_recent_uncached<=most_recent_cached:
			# cache is up to date
			return
		capacity_data = json.loads(capacity_cache[0].data)
		capacity_up = capacity_data[0]
		capacity_down = capacity_data[1]
		# retrieve all uncached measurements:
		uncached_capacity = all_measurements.filter(eventstamp__gt=most_recent_cached)
		if len(uncached_capacity)==0:
			return
		cap_measure_up = uncached_capacity.filter(direction='up').order_by('eventstamp')
		cap_measure_down = uncached_capacity.filter(direction='dw').order_by('eventstamp')
		capacity_data[0]['data'].extend(cvs_helper.linegraph_normal(cap_measure_up,'Capacity Up',1000,1,0,series_id)['data'])
		capacity_data[1]['data'].extend(cvs_helper.linegraph_normal(cap_measure_down,'Capacity Down',1000,1,0,series_id)['data'])
		capacity_cache[0].data=json.dumps(capacity_data)
		capacity_cache[0].eventstamp = most_recent_uncached
		capacity_cache[0].save()
	# cache is empty
	else:
		all_capacity= MCapacity.objects.filter(deviceid=device)
		# no measurements:
		if len(all_capacity)==0:
			return
		latest_capacity = all_capacity.latest('eventstamp').eventstamp
		cap_measure_up = all_capacity.filter(direction='up').order_by('eventstamp')
		cap_measure_down = all_capacity.filter(direction='dw').order_by('eventstamp')
		capacity_data.append(cvs_helper.linegraph_normal(cap_measure_up,'Capacity Up',1000,1,0,series_id))
		capacity_data.append(cvs_helper.linegraph_normal(cap_measure_down,'Capacity Down',1000,1,0,series_id))
		cache_capacity_new = JsonCache(deviceid = device, data =json.dumps(capacity_data), datatype = 'capacity', eventstamp = latest_capacity)
		cache_capacity_new.save()
	return
	
# appends new shaperate measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing.
def update_shaperate(device):
	series_id=5
	# series data for shaperate, in json format:
	shaperate_data = []
	# retrieve cached data:
	shaperate_cache = JsonCache.objects.filter(deviceid=device,datatype='shaperate')
	# cache already contains data:
	if len(shaperate_cache)!=0:
		all_measurements = MShaperate.objects.filter(deviceid=device)
		if len(all_measurements)==0:
			return
		most_recent_uncached = all_measurements.latest('eventstamp').eventstamp
		most_recent_cached = shaperate_cache[0].eventstamp
		if most_recent_uncached<= most_recent_cached:
			# up to date:
			return
		shaperate_data = json.loads(shaperate_cache[0].data)
		# split into 4 separate series, upload and download for shaperate and capacity:
		shaperate_up = shaperate_data[0]
		shaperate_down = shaperate_data[1]
		# retrieve all uncached measurements:
		uncached_shaperate = all_measurements.filter(eventstamp__gt=most_recent_cached)
		if len(uncached_shaperate)==0:
			return
		# separate shaperate records into upload and download
		shape_measure_up = uncached_shaperate.filter(direction='up').order_by('eventstamp')
		shape_measure_down = uncached_shaperate.filter(direction='dw').order_by('eventstamp')
		# convert records to series data and append to cached data:
		shaperate_data[0]['data'].extend(cvs_helper.linegraph_normal(shape_measure_up,'Shape rate Up',1000,1,0,series_id)['data'])
		shaperate_data[1]['data'].extend(cvs_helper.linegraph_normal(shape_measure_down,'Shape rate Down',1000,1,1,series_id)['data'])
		shaperate_cache[0].data=json.dumps(shaperate_data)
		shaperate_cache[0].eventstamp = most_recent_uncached
		shaperate_cache[0].save()
	# 1 or both caches are empty:
	else:
		# retrieve all capacity and shaperate measurement records for this device:
		all_shaperate= MShaperate.objects.filter(deviceid=device)
		if len(all_shaperate)==0:
			# no data
			return
		most_recent_cached = all_shaperate.latest('eventstamp').eventstamp
		# separate shaperate records into upload and download:
		shape_measure_up = all_shaperate.filter(direction='up').order_by('eventstamp')
		shape_measure_down = all_shaperate.filter(direction='dw').order_by('eventstamp')
		# convert records into new series to be placed in cache:
		shaperate_data.append(cvs_helper.linegraph_normal(shape_measure_up,'Shape rate Up',1000,1,0,series_id))
		shaperate_data.append(cvs_helper.linegraph_normal(shape_measure_down,'Shape rate Down',1000,1,1,series_id))
		cache_shaperate_new = JsonCache(deviceid = device, data = json.dumps(shaperate_data), datatype = 'shaperate', eventstamp = most_recent_cached)
		cache_shaperate_new.save()
	return	

# appends new underload measurements to precomputed (cached) JSON dictionaries for each device. This method updates
# a db record and returns nothing.
def update_unload(device):
	series_id=6
	# series data in json format:
	unload_data = []
	# retrieve cached data:
	unload_cache = JsonCache.objects.filter(deviceid=device,datatype='unload')
	# cache not empty:
	if len(unload_cache)!=0:
		all_upload = MUlrttup.objects.filter(deviceid=device)
		all_download = MUlrttdw.objects.filter(deviceid=device)
		# no measurements:
		if len(all_upload)==0 and len(all_download)==0:
			return
		most_recent_cached = unload_cache.latest('eventstamp').eventstamp
		most_recent_uncached_up = all_upload.latest('eventstamp').eventstamp
		most_recent_uncached_down = all_download.latest('eventstamp').eventstamp
		if most_recent_uncached_up<=most_recent_cached and most_recent_uncached_down<=most_recent_cached:
			# cache is up to date
			return
		unload_data = json.loads(unload_cache[0].data)
		if most_recent_uncached_up>most_recent_cached:
			# retrieve all uncached measurements:
			uncached_up = all_upload.filter(eventstamp__gt=most_recent_cached)
			if len(uncached_up)!=0:
				uncached_up = uncached_up.order_by('eventstamp')
				unload_data[1]['data'].extend(cvs_helper.linegraph_normal(uncached_up,'Under Load Up',1,1,0,series_id)['data'])
		if most_recent_uncached_down>most_recent_cached:
			# retrieve all uncached measurements:
			uncached_down = all_download.filter(eventstamp__gt=most_recent_cached)
			if len(uncached_down)!=0:
				uncached_down = uncached_down.order_by('eventstamp')
				unload_data[0]['data'].extend(cvs_helper.linegraph_normal(uncached_down,'Under Load Down',1,1,0,series_id)['data'])
		if most_recent_uncached_down>most_recent_uncached_up:
			most_recent_uncached = most_recent_uncached_down
		else:
			most_recent_uncached = most_recent_uncached_up
		unload_cache[0].data=json.dumps(unload_data)
		unload_cache[0].eventstamp = most_recent_uncached
		unload_cache[0].save()
	# cache is empty
	else:
		all_upload = MUlrttup.objects.filter(deviceid=device)
		all_download = MUlrttdw.objects.filter(deviceid=device)
		# no measurements:
		if len(all_upload)==0 or len(all_download)==0:
			return
		latest_upload = all_upload.latest('eventstamp').eventstamp
		latest_download = all_download.latest('eventstamp').eventstamp
		if latest_upload<latest_download:
			latest_eventstamp = latest_download
		else:
			latest_eventstamp = latest_upload
		all_upload = all_upload.order_by('eventstamp')
		all_download = all_download.order_by('eventstamp')
		unload_data.append(cvs_helper.linegraph_normal(all_download,'Under Load Down',1,1,0,series_id))
		unload_data.append(cvs_helper.linegraph_normal(all_upload,'Under Load Up',1,1,0,series_id))
		cache_unload_new = JsonCache(deviceid = device, data =json.dumps(unload_data), datatype = 'unload', eventstamp = latest_eventstamp)
		cache_unload_new.save()
	return
	
# creates and returns series for lmrtt measurements for devices in a given city:	
def compare_lmrtt_by_city(city,max_results,days):
	# Calculate earliest date of the series based on user selection:
	earliest = datetime_helper.get_daterange_start(days)
	devices = views_helper.get_devices_by_city_name(city)
	# Create list of lists. The first list contains data series for the linegraph.
	# The second contains series for the bar graph (averages):
	result = [[] for x in range(2)]
	result_count = 0
	isps = []
	for dev in devices:
		if(result_count == max_results):
			break
		latest_measurements= MLmrtt.objects.filter(average__lte=3000, deviceid=dev, eventstamp__gte=earliest).order_by('eventstamp')
		if len(latest_measurements)==0:
			continue
		else:
			data= latest_measurements.order_by('eventstamp')
			isp = geoip_helper.get_isp_by_device(dev)
			isps.append(isp)
			isp_count=0
			for included_isp in isps:
				if included_isp == isp:
					isp_count++
			series_name = isp + ' ' + str(isp_count)
			graph_data = cvs_helper.linegraph_compare(data,series_name,1,1,2)
			result[0].append(graph_data[0])
			result[1].append(graph_data[1])
			result_count += 1
	return result
	
def compare_rtt_by_city(city,max_results,days):
	# Calculate earliest date of the series based on user selection:
	earliest = datetime_helper.get_daterange_start(days)
	devices = views_helper.get_devices_by_city_name(city)
	# Create list of lists. The first list contains data series for the linegraph.
	# The second contains series for the bar graph (averages):
	result = [[] for x in range(2)]
	isps = []
	for dev in devices:
		if(result_count == max_results):
			break
		latest_measurements= MRtt.objects.filter(average__lte=3000, deviceid=dev, eventstamp__gte=earliest, dstip='4.71.254.153')
		if len(latest_measurements)==0:
			continue
		else:
			data= latest_measurements.order_by('eventstamp')
			isp = geoip_helper.get_isp_by_device(dev)
			isps.append(isp)
			isp_count=0
			for included_isp in isps:
				if included_isp == isp:
					isp_count++
			series_name = isp + ' ' + str(isp_count)
			graph_data = cvs_helper.linegraph_compare(data,series_name,1,1,2)
			result[0].append(graph_data[0])
			result[1].append(graph_data[1])
			result_count += 1
	return result

# creates and returns series for bitrate measurements for devices in a given city:	
def compare_bitrate_by_city(city,max_results,days,dir):
	devices = views_helper.get_devices_by_city_name(city)
	# Calculate earliest date of the series based on user selection:
	earliest = datetime_helper.get_daterange_start(days)
	# Create list of lists. The first list contains data series for the linegraph.
	# The second contains series for the bar graph (averages):
	result = [[] for x in range(2)]
	result_count = 0
	isps = []
	for dev in devices:
		if(result_count == max_results):
			break
		recent_measurements = MBitrate.objects.filter(deviceid = dev, direction = dir, toolid='NETPERF_3', eventstamp__gte=earliest)
		if len(recent_measurements)==0:
			continue
		else:
			data = recent_measurements.order_by('eventstamp')
			isp = geoip_helper.get_isp_by_device(dev)
			isps.append(isp)
			isp_count=0
			for included_isp in isps:
				if included_isp == isp:
					isp_count++
			series_name = isp + ' ' + str(isp_count)
			graph_data = cvs_helper.linegraph_compare(data,series_name,1000,18000,2)
			result[0].append(graph_data[0])
			result[1].append(graph_data[1])
			result_count += 1
	return result


def fetch_deviceid_soft(device):
    device_search = Devicedetails.objects.filter(deviceid=device)
    try:
        if len(device_search)>0:
            return True
    except:
        pass

    return False
    

def fetch_deviceid_hard(device):
    
    device_search = MBitrate.objects.filter(deviceid=device)

    try:
        if (len(device_search)>0):
            return True
    except:

        device_search = MRtt.objects.filter(deviceid=device)

    try:
        if (len(device_search)>0):
            return True
    except:
        device_search = MLmrtt.objects.filter(deviceid=device)


    try:
        if (len(device_search)>0):
            return True
    except:
        pass
    
    return False

def list_isps():
    ret = ["Comcast","Time Warner Cable","At&t","Cox Optimum","Charter","Verizon","CenturyLink","SuddenLink","EarthLink","Windstream","Cable One","Frontier","NetZero Juno","Basic ISP","ISP.com","PeoplePC","AOL MSN","Fairpoint","Qwest","CableVision","MEdiaCom"]
    ret.sort()
    return ret

def device_count_and_country_data():
	distinct_countries = list_countries()
	response = []
	for country in distinct_countries:
		if country!='':
			value={}
			count = device_count_for_country(country)
			value['country']=country
			value['count']=count
			response.append(value) 
	return response
	
def get_isp_count():
	distinct_isps = list_isps()
	response = []
	for isp in distinct_isps:
		if isp!='':
			value={}
			count = device_count_for_isp(isp)
			value['isp']=isp
			value['count']=count
			response.append(value) 
	return response

def device_count_for_country(cntry):
    return len(Devicedetails.objects.filter(country=cntry))
	
def device_count_for_isp(provider):
    return len(Devicedetails.objects.filter(isp=provider))
    

def list_countries():
    ret=[]
    out = Devicedetails.objects.values('country').distinct()
    for one in out:
        value = ast.literal_eval(str(one))
        v = value['country']
        ret.append(v)
    ret.sort()
    return ret
	
def list_isps():
    ret=[]
    out = Devicedetails.objects.values('isp').distinct()
    for one in out:
        value = ast.literal_eval(str(one))
        v = value['isp']
        ret.append(v)
    ret.sort()
    return ret

def get_num_common_locations(device_details):
    return len(Devicedetails.objects.filter(city=device_details.city))-1

def get_num_common_providers(device_details):
    return len(Devicedetails.objects.filter(isp=device_details.isp))-1

def get_num_devices(device_details):
    return len(Devicedetails.objects.exclude(deviceid=device_details.deviceid))-1

def get_first_measurement(device):
	try:
		first = MBitrate.objects.filter(deviceid=device).order_by('eventstamp')[0:3]    
		return first[0].eventstamp.strftime("%B %d, %Y")
	except:
		return None

def get_last_measurement(device):
	try:
		last = MBitrate.objects.filter(deviceid=device).order_by('-eventstamp')[0:3]
		return last[0].eventstamp.strftime("%B %d, %Y")
	except:
		return None
	
def get_latest_download(device):
	latest = MBitrate.objects.filter(deviceid=device).order_by('-eventstamp')
	latest = latest.filter(dstip = '143.215.131.173')
	ret = {}
	try:
		ret['average']= latest[0].average
		ret['eventstamp']= latest[0].eventstamp.strftime("%B %d, %Y, %I:%M %p")
	except:
		return ret
	return ret

def get_latest_upload(device):
	latest = MBitrate.objects.filter(deviceid=device).order_by('-eventstamp')
	latest = latest.filter(srcip = '143.215.131.173')
	ret = {}
	try:
		ret['average']= latest[0].average
		ret['eventstamp']= latest[0].eventstamp.strftime("%B %d, %Y, %I:%M %p")
	except:
		return ret
	return ret

def get_latest_lastmile(device):
	latest = MLmrtt.objects.filter(deviceid=device,average__lte=3000).order_by('-eventstamp')
	ret = {}
	try:
		ret['average']= latest[0].average
		ret['eventstamp']= latest[0].eventstamp.strftime("%B %d, %Y, %I:%M %p")
	except:
		return ret
	return ret

def get_latest_roundtrip(device):
	latest = MRtt.objects.filter(deviceid=device,average__lte=3000).order_by('-eventstamp')	
	ret = {}
	try:
		ret['average']= latest[0].average
		ret['eventstamp']= latest[0].eventstamp.strftime("%B %d, %Y, %I:%M %p")
	except:
		return ret
	return ret
	
def get_latest_shaperate(device):
	latest = MShaperate.objects.filter(deviceid=device,average__lte=300).order_by('-eventstamp')
	ret = {}
	try:
		ret['average']= latest[0].average
		ret['eventstamp']= latest[0].eventstamp.strftime("%B %d, %Y, %I:%M %p")
	except:
		return ret
	return ret


def get_location(device):
    device = device.replace(':','')
    details = Devicedetails.objects.filter(deviceid=device)
    if len(details)>0:
        return (details[0].city + ", " + details[0].country)

    dev = MBitrate.objects.filter(deviceid=device, srcip ='143.215.131.173' )
    if len(dev)>0:
        ip = str(dev[0].dstip)
        urlobj=urllib2.urlopen("http://api.ipinfodb.com/v3/ip-city/?key=c91c266accebc12bc7bbdd7fef4b5055c1485208bb6c20b4cc2991e67a3e3d34&ip=" + ip + "&format=json")
        r1 = urlobj.read()
        urlobj.close()
        datadict = json.loads(r1)
        res = datadict["cityName"] + "," + datadict["countryName"]
        return (res)  
    
    return ('unavailable')

def get_google_maps_result_from_request(address):
    params = urllib.urlencode({'key': 'AIzaSyBHEmkA7XyusAjA9Zf-UnLSR9ydvCExY6k', 'output': 'json', 'q': str(address)})
    f = urllib2.urlopen("http://maps.google.com/maps/geo?"+str(params))
    result = ast.literal_eval(f.read())
    return result

def save_device_details_from_request(request,device):
	hashing = views_helper.get_hash(device)
	dname = request.POST.get('name')
	disp = request.POST.get('isp')
	dlocation = request.POST.get('location')
	dsp = request.POST.get('sp')
	dservicetype = request.POST.get('servicetype')
	durate = int(request.POST.get('urate'))
	ddrate = int(request.POST.get('drate'))
	dcity = request.POST.get('city')
	dstate = request.POST.get('state')
	dcountry = request.POST.get('country')        
	details = Devicedetails(deviceid = device, name = dname, isp = disp, serviceplan = dsp, servicetype=dservicetype,city = dcity, state = dstate, country = dcountry, uploadrate = durate, downloadrate = ddrate, eventstamp = datetime.now(),hashkey=hashing)

	try:
		address = dcity+","+dstate+","+dcountry
		result = get_google_maps_result_from_request(str(address))
		if result['Status']['code'] == 200:
   
		    coord=result['Placemark'][0]['Point']['coordinates']
		    details.latitude = coord[1]
		    details.longitude=coord[0]
		    details.country=result['Placemark'][0]['AddressDetails']['Country']['CountryName']
		    details.state=result['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['AdministrativeAreaName']
		    details.city=result['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['Locality']['LocalityName']
	except Exception as inst:
		print type(inst)
		print inst
       
	details.is_default=False
	details.save()

def save_device_details_from_default(device):
    hashing = views_helper.get_hash(device)
    device_entry = Devicedetails(
            deviceid=device, eventstamp=datetime.now(), name="default name",
            hashkey=hashing, is_default=True)
    device_entry.save()

def deviceid_to_nodeid(device):
    return "OW" + device.upper()
	