# train_api/utils.py
import time
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup # For LiveStation

# Helper to get current timestamp in milliseconds
def _current_timestamp_ms():
    return int(time.time() * 1000)

def between_station_logic(api_response_text: str):
    try:
        retval = {}
        arr = []
        
        # Initial check for specific error messages
        # Note: In JS, data[0] was checked. Here, we check the beginning of the string after splitting.
        # The JS code `data = string.split("~~~~~~~~"); nore = data[0].split("~"); nore = nore[5].split("<");`
        # is a bit convoluted if it's just for the "No direct trains" message.
        # Let's simplify the error checking based on the provided JS logic.

        if "No direct trains found" in api_response_text: # Simplified check
            first_part_for_no_direct = api_response_text.split("~~~~~~~~")[0]
            # Example: "SL,CLASS,~,~,~,No direct trains found<br>Try options"
            # The JS splits by ~ and takes 5th element, then splits by < and takes 0th.
            try:
                nore_check_parts = first_part_for_no_direct.split("~")
                if len(nore_check_parts) > 5:
                    message_part = nore_check_parts[5].split("<")[0]
                    if message_part == "No direct trains found":
                        retval["success"] = False
                        retval["time_stamp"] = _current_timestamp_ms()
                        retval["data"] = message_part
                        return retval
            except IndexError:
                pass # If splitting doesn't work, proceed to other checks/parsing

        # Check for other specific full-string error messages from the JS
        # JS: data[0] === "~~~~~Please try again after some time."
        # This implies string itself might start with these after the first split by ~~~~~~~~
        # Or, the string itself is just that error message.
        # Assuming these are exact matches for the first segment if data is split by "~~~~~~~~"
        # For robustness, we can check if the api_response_text *contains* these key phrases
        # if it's not structured data.

        # The JS `data = string.split("~~~~~~~~"); if (data[0] === "~~~~~Please try again after some time.")`
        # implies data[0] can be exactly "~~~~~Please try again after some time."
        
        potential_error_messages = [
            "~~~~~Please try again after some time.",
            "~~~~~From station not found",
            "~~~~~To station not found"
        ]
        
        # If the string starts with one of these (typical for single error responses)
        first_segment_error_check = api_response_text.split("~~~~~~~~")[0]
        if first_segment_error_check in potential_error_messages:
            retval["success"] = False
            retval["time_stamp"] = _current_timestamp_ms()
            retval["data"] = first_segment_error_check.replace("~", "")
            return retval

        data_segments = api_response_text.split("~~~~~~~~")
        data_segments = [el for el in data_segments if el] # Filter out empty strings

        if not data_segments and not retval: # If after all checks, no data and no error set
            retval["success"] = False
            retval["time_stamp"] = _current_timestamp_ms()
            retval["data"] = "Unknown error or empty response from API."
            return retval
            
        for segment in data_segments:
            parts = segment.split("~^")
            if len(parts) == 2:
                train_data_str = parts[1]
                train_details = [el for el in train_data_str.split("~") if el]

                if len(train_details) >= 14: # Ensure enough data points
                    obj = {
                        "train_no": train_details[0],
                        "train_name": train_details[1],
                        "source_stn_name": train_details[2],
                        "source_stn_code": train_details[3],
                        "dstn_stn_name": train_details[4],
                        "dstn_stn_code": train_details[5],
                        "from_stn_name": train_details[6],
                        "from_stn_code": train_details[7],
                        "to_stn_name": train_details[8],
                        "to_stn_code": train_details[9],
                        "from_time": train_details[10],
                        "to_time": train_details[11],
                        "travel_time": train_details[12],
                        # "running_days": train_details[13], # This needs to be parsed into a list/array
                    }
                    # Parse running_days string "YNNYYNY" into [1,0,0,1,1,0,1]
                    # Assuming Y=1, N=0. The order depends on erail's convention (e.g., Mon-Sun or Sun-Sat)
                    # The JS getDayOnDate output suggests an indexing that might match this.
                    # For now, let's store it as a string, or parse it if the convention is known.
                    # Example: Monday to Sunday
                    raw_running_days = train_details[13]
                    parsed_running_days = [1 if day_char == 'Y' else 0 for day_char in raw_running_days]
                    if len(parsed_running_days) == 7: # Standard 7 days
                         obj["running_days_str"] = raw_running_days # Keep original string
                         obj["running_days"] = parsed_running_days # Parsed list
                    else: # Fallback or handle error
                        obj["running_days_str"] = raw_running_days
                        obj["running_days"] = [] # Or some error indicator


                    train_base_obj = {"train_base": obj}
                    arr.append(train_base_obj)
        
        if not arr and not retval.get("success", True): # If parsing failed to produce any trains and no prior error set
             retval["success"] = False
             retval["time_stamp"] = _current_timestamp_ms()
             retval["data"] = "No train data could be parsed."
             return retval
        elif not arr and retval.get("success", True) : # No error but no data found, this shouldn't happen if check above works
             retval["success"] = False # Or True if an empty list of trains is a valid success
             retval["time_stamp"] = _current_timestamp_ms()
             retval["data"] = "No direct trains found or data format issue." # More specific message
             return retval


        retval["success"] = True
        retval["time_stamp"] = _current_timestamp_ms()
        retval["data"] = arr
        return retval

    except Exception as e:
        # Log the error properly in a real application
        print(f"Error in between_station_logic: {e} with data: {api_response_text[:200]}") # Log snippet of data
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"An error occurred during data processing: {str(e)}",
        }


def get_day_on_date_logic(dd_str: str, mm_str: str, yyyy_str: str) -> int:
    """
    Converts date to a specific day index.
    JS logic: `date.getDay() >= 0 && date.getDay() <= 2 ? date.getDay() + 4 : date.getDay() - 3;`
    JS getDay(): Sun=0, Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6
    Mapping from JS: Wed (0), Thu (1), Fri (2), Sat (3), Sun (4), Mon (5), Tue (6)

    Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    The required Python mapping: (python_weekday + 5) % 7
    """
    try:
        dd = int(dd_str)
        mm = int(mm_str) # JS Date uses 0-indexed month if numbers, but from string it's fine.
        yyyy = int(yyyy_str)
        
        # Python's datetime takes month 1-indexed
        date_obj = datetime(yyyy, mm, dd)
        
        py_weekday = date_obj.weekday() # Mon:0, Tue:1, Wed:2, Thu:3, Fri:4, Sat:5, Sun:6
        
        # Target mapping based on JS: Wed(0), Thu(1), Fri(2), Sat(3), Sun(4), Mon(5), Tue(6)
        # Mon (0) -> 5
        # Tue (1) -> 6
        # Wed (2) -> 0
        # Thu (3) -> 1
        # Fri (4) -> 2
        # Sat (5) -> 3
        # Sun (6) -> 4
        # This is equivalent to (py_weekday + 5) % 7
        mapped_day_index = (py_weekday + 5) % 7
        return mapped_day_index
    except ValueError:
        print(f"Invalid date components for get_day_on_date_logic: {dd_str}-{mm_str}-{yyyy_str}")
        return -1 # Indicate error, consistent with how your Django view might check

def get_route_logic(api_response_text: str):
    try:
        retval = {}
        arr = []
        
        data_segments = api_response_text.split("~^")
        data_segments = [el for el in data_segments if el]

        if not data_segments:
            return {
                "success": False,
                "time_stamp": _current_timestamp_ms(),
                "data": "No route data found in response."
            }

        for segment in data_segments:
            details = [el for el in segment.split("~") if el]
            # JS code implies specific indices, ensure they exist
            if len(details) > 9: # Check based on max index used (9 for zone)
                obj = {
                    "source_stn_name": details[2],
                    "source_stn_code": details[1],
                    "arrive": details[3],
                    "depart": details[4],
                    "distance": details[6],
                    "day": details[7],
                    "zone": details[9]
                }
                arr.append(obj)
        
        if not arr: # If segments were present but no valid details extracted
            return {
                "success": False,
                "time_stamp": _current_timestamp_ms(),
                "data": "Could not parse route details from segments."
            }

        retval["success"] = True
        retval["time_stamp"] = _current_timestamp_ms()
        retval["data"] = arr
        return retval
    except Exception as e:
        print(f"Error in get_route_logic: {e}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"An error occurred: {str(e)}",
        }

def live_station_logic(soup: BeautifulSoup): # Expects a BeautifulSoup object
    try:
        arr = []
        retval = {}

        # JS: $('.name').each((i,el)=>{...})
        for item_name_el in soup.select('.name'):
            obj = {}
            
            # train_no and train_name from item_name_el.text
            full_train_text = item_name_el.get_text(strip=True)
            obj["train_no"] = full_train_text[:5]
            obj["train_name"] = full_train_text[5:].strip()

            # source_stn_name and dstn_stn_name from next div
            next_div = item_name_el.find_next_sibling("div")
            if next_div:
                div_text = next_div.get_text(strip=True)
                source_dest_parts = div_text.split("→")
                obj["source_stn_name"] = source_dest_parts[0].strip() if len(source_dest_parts) > 0 else ""
                obj["dstn_stn_name"] = source_dest_parts[1].strip() if len(source_dest_parts) > 1 else ""
            else:
                obj["source_stn_name"] = ""
                obj["dstn_stn_name"] = ""
            
            # time_at and detail from parent td's next td
            parent_td = item_name_el.find_parent("td")
            if parent_td:
                next_status_td = parent_td.find_next_sibling("td")
                if next_status_td:
                    status_text = next_status_td.get_text(strip=True)
                    obj["time_at"] = status_text[:5]
                    obj["detail"] = status_text[5:].strip() # In JS this was just slice(5)
                else:
                    obj["time_at"] = ""
                    obj["detail"] = ""
            else:
                obj["time_at"] = ""
                obj["detail"] = ""
            
            arr.append(obj)
        
        retval["success"] = True
        retval["time_stamp"] = _current_timestamp_ms()
        retval["data"] = arr
        return retval
    except Exception as e:
        print(f"Error in live_station_logic: {e}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"An error occurred during HTML parsing: {str(e)}",
        }

def pnr_status_logic(html_string: str):
    retval = {}
    try:
        # JS: var pattern = /data\s*=\s*({.*?;})/
        # JS: let match = string.match(pattern)[0].slice(7,-1)
        # Python: Use re.search to find the pattern and extract the group
        match = re.search(r"data\s*=\s*({.*?});", html_string, re.DOTALL) # re.DOTALL in case JSON spans newlines
        
        if match:
            json_data_string = match.group(1) # Group 1 is the ({.*?}) part
            parsed_data = json.loads(json_data_string) # Parse the extracted JSON string
            
            retval["success"] = True
            retval["time_stamp"] = _current_timestamp_ms()
            retval["data"] = parsed_data
        else:
            retval["success"] = False
            retval["time_stamp"] = _current_timestamp_ms()
            retval["data"] = "Could not find PNR data in the page."
            
        return retval
    except json.JSONDecodeError as e:
        print(f"JSON parsing error in pnr_status_logic: {e}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": "Failed to parse PNR data from page.",
        }
    except Exception as e:
        print(f"Error in pnr_status_logic: {e}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"An error occurred: {str(e)}",
        }

def check_train_logic(api_response_text: str):
    try:
        retval = {}
        
        # JS: data[0] === "~~~~~Please try again after some time." || data[0] === "~~~~~Train not found"
        # This implies the entire response or the first segment after split is the error
        first_segment_error_check = api_response_text.split("~~~~~~~~")[0]
        error_messages = [
            "~~~~~Please try again after some time.",
            "~~~~~Train not found"
        ]
        if first_segment_error_check in error_messages:
            retval["success"] = False
            retval["time_stamp"] = _current_timestamp_ms()
            retval["data"] = first_segment_error_check.replace("~", "")
            return retval

        data_segments = api_response_text.split("~~~~~~~~")
        
        if len(data_segments) < 2: # Expecting at least two segments for train details
             return {
                "success": False,
                "time_stamp": _current_timestamp_ms(),
                "data": "Invalid data format for train details."
            }

        # Process first segment for primary details
        details_part1_str = data_segments[0]
        details_part1 = [el for el in details_part1_str.split("~") if el]
        
        # JS: if (data1[1].length > 6) { data1.shift(); }
        # This implies some conditional prefix or format issue on details_part1[1]
        # Assuming details_part1[0] might be an empty string or some flag
        if details_part1 and len(details_part1) > 1 and len(details_part1[1]) > 6: # Check if details_part1[1] is the train number
            # A common pattern in erail text is like "^12345" for train number,
            # if details_part1[0] is empty after split, details_part1[1] would be details_part1_str.split("~")[1]
            # If the first element is garbage, shift.
            # This logic is tricky without seeing the exact string that triggers it.
            # For now, let's assume this means if the *second element after filtering* is too long to be a train number prefix,
            # then we discard the *first element after filtering*.
            if details_part1[0] == '^': # A common prefix if the split puts ^ as its own element
                details_part1.pop(0)
            elif len(details_part1[0]) > 6 and len(details_part1) > 1 and not details_part1[0].isdigit(): # If first element looks wrong
                details_part1.pop(0)


        # Ensure enough elements after potential shift for all indexed accesses
        # Max index used for part1 is 14 (running_days)
        if len(details_part1) < 15:
             return {
                "success": False,
                "time_stamp": _current_timestamp_ms(),
                "data": "Not enough data in the first part of train details."
            }

        obj = {
            "train_no": details_part1[0].replace("^", ""), # JS used details_part1[1] after shift logic
            "train_name": details_part1[1],
            "from_stn_name": details_part1[2],
            "from_stn_code": details_part1[3],
            "to_stn_name": details_part1[4],
            "to_stn_code": details_part1[5],
            "from_time": details_part1[10],
            "to_time": details_part1[11],
            "travel_time": details_part1[12],
            # "running_days": details_part1[13], # Similar parsing as in BetweenStation
        }
        raw_running_days_ct = details_part1[13] # JS used 14
        parsed_running_days_ct = [1 if day_char == 'Y' else 0 for day_char in raw_running_days_ct]
        if len(parsed_running_days_ct) == 7:
            obj["running_days_str"] = raw_running_days_ct
            obj["running_days"] = parsed_running_days_ct
        else:
            obj["running_days_str"] = raw_running_days_ct
            obj["running_days"] = []


        # Process second segment for additional details
        details_part2_str = data_segments[1]
        details_part2 = [el for el in details_part2_str.split("~") if el]

        # Max index used for part2 is 19
        if len(details_part2) < 20:
            return {
                "success": False,
                "time_stamp": _current_timestamp_ms(),
                "data": "Not enough data in the second part of train details."
            }

        obj["type"] = details_part2[11]  # JS used index 11
        obj["train_id"] = details_part2[12] # JS used index 12
        obj["distance_from_to"] = details_part2[18]
        obj["average_speed"] = details_part2[19]
        
        retval["success"] = True
        retval["time_stamp"] = _current_timestamp_ms()
        retval["data"] = obj
        return retval

    except IndexError as e:
        print(f"Index error in check_train_logic: {e}. Data: {api_response_text[:200]}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"Data parsing error (index out of bounds): {str(e)}",
        }
    except Exception as e:
        print(f"Error in check_train_logic: {e}. Data: {api_response_text[:200]}")
        return {
            "success": False,
            "time_stamp": _current_timestamp_ms(),
            "data": f"An error occurred: {str(e)}",
        }