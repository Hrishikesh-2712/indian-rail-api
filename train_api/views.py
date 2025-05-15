from django.http import JsonResponse
import httpx # For asynchronous HTTP requests
import time
from user_agents import parse as ua_parse # For User-Agent generation
from bs4 import BeautifulSoup # For HTML parsing

from . import utils # Our prettify equivalents

# Create an asynchronous HTTP client session to be reused
# It's good practice to create it once if you're making many requests.
# For simplicity in these examples, we'll create it per request,
# but for high-load applications, consider managing a global or app-level client.

async def get_train_view(request):
    train_no = request.GET.get('trainNo')
    if not train_no:
        return JsonResponse({'success': False, 'error': 'trainNo parameter is required'}, status=400)

    url_train = f"https://erail.in/rail/getTrains.aspx?TrainNo={train_no}&DataSource=0&Language=0&Cache=true"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url_train, timeout=10.0) # Added timeout
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            data_text = response.text
        
        json_response_data = utils.check_train_logic(data_text)
        return JsonResponse(json_response_data)
    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e: # Catches network errors, timeouts, etc.
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


async def between_stations_view(request):
    station_from = request.GET.get('from')
    station_to = request.GET.get('to')

    if not station_from or not station_to:
        return JsonResponse({'success': False, 'error': 'Both from and to parameters are required'}, status=400)

    url_trains = (f"https://erail.in/rail/getTrains.aspx?Station_From={station_from}"
                  f"&Station_To={station_to}&DataSource=0&Language=0&Cache=true")
    
    try:
        user_agent_string = str(ua_parse("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")) # Generate a user agent
        headers = {'User-Agent': user_agent_string}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url_trains, headers=headers, timeout=10.0)
            response.raise_for_status()
            data_text = response.text
            
        json_response_data = utils.between_station_logic(data_text)
        return JsonResponse(json_response_data)
    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e:
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in between_stations_view: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)


async def get_train_on_view(request):
    station_from = request.GET.get('from')
    station_to = request.GET.get('to')
    date_str = request.GET.get('date') # e.g., "25-12-2023" DD-MM-YYYY

    retval = {}

    if not all([station_from, station_to, date_str]):
        return JsonResponse({
            "success": False,
            "time_stamp": int(time.time() * 1000),
            "data": "Parameters 'from', 'to', and 'date' are required."
        }, status=400)

    try:
        dd, mm, yyyy = date_str.split("-")
    except ValueError:
        return JsonResponse({
            "success": False,
            "time_stamp": int(time.time() * 1000),
            "data": "Invalid date format. Please use DD-MM-YYYY."
        }, status=400)

    url_trains = (f"https://erail.in/rail/getTrains.aspx?Station_From={station_from}"
                  f"&Station_To={station_to}&DataSource=0&Language=0&Cache=true")
    
    try:
        user_agent_string = ua_parse("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36").toString()
        headers = {'User-Agent': user_agent_string}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url_trains, headers=headers, timeout=10.0)
            response.raise_for_status()
            data_text = response.text

        initial_json = utils.between_station_logic(data_text)

        if not initial_json.get("success"):
            return JsonResponse(initial_json)

        day_index = utils.get_day_on_date_logic(dd, mm, yyyy)
        if day_index == -1: # Invalid date from util
             return JsonResponse({
                "success": False,
                "time_stamp": int(time.time() * 1000),
                "data": "Invalid date provided for processing."
            }, status=400)


        filtered_trains = []
        if initial_json.get("data") and isinstance(initial_json["data"], list):
            for train_details in initial_json["data"]:
                # Ensure the path to running_days is correct as per your actual utils.between_station_logic output
                running_days = train_details.get("train_base", {}).get("running_days", [])
                if 0 <= day_index < len(running_days) and running_days[day_index] == 1:
                    filtered_trains.append(train_details)
        
        retval["success"] = True
        retval["time_stamp"] = int(time.time() * 1000)
        retval["data"] = filtered_trains
        return JsonResponse(retval)

    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e:
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error in get_train_on_view: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)


async def get_route_view(request):
    train_no = request.GET.get('trainNo')
    if not train_no:
        return JsonResponse({'success': False, 'error': 'trainNo parameter is required'}, status=400)

    url_train_details = f"https://erail.in/rail/getTrains.aspx?TrainNo={train_no}&DataSource=0&Language=0&Cache=true"

    try:
        async with httpx.AsyncClient() as client:
            # First call to get train details (and train_id)
            response_details = await client.get(url_train_details, timeout=10.0)
            response_details.raise_for_status()
            details_text = response_details.text
            
            train_info_json = utils.check_train_logic(details_text)
            if not train_info_json.get("success") or not train_info_json.get("data"):
                return JsonResponse(train_info_json)

            train_id = train_info_json["data"].get("train_id")
            if not train_id:
                 return JsonResponse({'success': False, 'error': 'Could not extract train_id from initial train data.'}, status=500)

            # Second call to get the route
            url_route = (f"https://erail.in/data.aspx?Action=TRAINROUTE&Password=2012"
                         f"&Data1={train_id}&Data2=0&Cache=true")
            
            response_route = await client.get(url_route, timeout=10.0)
            response_route.raise_for_status()
            route_text = response_route.text
            
            route_json = utils.get_route_logic(route_text)
            return JsonResponse(route_json) # Note: Express used resp.send(), JsonResponse is typical for dicts

    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e:
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error in get_route_view: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)


async def station_live_view(request):
    station_code = request.GET.get('code')
    if not station_code:
        return JsonResponse({'success': False, 'error': 'code parameter (station code) is required'}, status=400)

    url_live = f"https://erail.in/station-live/{station_code}?DataSource=0&Language=0&Cache=true"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url_live, timeout=10.0)
            response.raise_for_status()
            html_data = response.text
        
        # Parse HTML using BeautifulSoup (equivalent to Cheerio)
        soup = BeautifulSoup(html_data, 'html.parser')
        
        json_response_data = utils.live_station_logic(soup) # Pass the soup object
        return JsonResponse(json_response_data) # Note: Express used resp.send()

    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e:
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error in station_live_view: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)

async def pnr_status_view(request):
    pnr_number = request.GET.get('pnr')
    if not pnr_number:
        return JsonResponse({'success': False, 'error': 'pnr parameter is required'}, status=400)

    url_pnr = f"https://www.confirmtkt.com/pnr-status/{pnr_number}"
    
    try:
        async with httpx.AsyncClient() as client:
            # confirmtkt might be sensitive to user agents or require specific headers
            # For now, a standard request:
            response = await client.get(url_pnr, timeout=15.0) # Longer timeout as PNR status can be slow
            response.raise_for_status()
            data_text = response.text # This could be HTML or a JSON string in script tag

        # The utils.pnr_status_logic will need to handle whether data_text is HTML to be parsed
        # or if it's some other format.
        json_response_data = utils.pnr_status_logic(data_text)
        return JsonResponse(json_response_data) # Note: Express used resp.send()

    except httpx.HTTPStatusError as e:
        return JsonResponse({'success': False, 'error': f'HTTP error: {e.response.status_code} - {e.response.text}'}, status=e.response.status_code)
    except httpx.RequestError as e:
        return JsonResponse({'success': False, 'error': f'Request failed: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error in pnr_status_view: {e}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)