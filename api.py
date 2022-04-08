import logging
import config
import xml.etree.ElementTree as ET
from pydantic import BaseModel, validator
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from requests import Session, HTTPError
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


API_KEY = config.api_key
logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.DEBUG)

# These error codes can be retried according to google. Ref: https://github.com/googlemaps/google-maps-services-python/blob/4dd8db6b53049869cf98f2fed3ba8e56676d1709/googlemaps/client.py#L214
retry_strategy = Retry(total=5, status_forcelist=[
    500, 503, 504], backoff_factor=2)
adapter = HTTPAdapter(max_retries=retry_strategy)
session_object = Session()
session_object.mount("https://", adapter)
session_object.mount("http://", adapter)

app = FastAPI(title="Priyanka Verloop FDE Assignment", version="0.0.1", contact={
    "name": "S Priyanka",
    "url": "https://www.linkedin.com/in/priyanka-s-1a85ab184",
    "email": "priyankasrinivasan125@gmail.com",
}, docs_url="/")


class AddressDetailsParameters(BaseModel):
    """Class to validate request parameters for /getAddressDetails

    Args:
        BaseModel: Base class for validators

    Raises:
        HTTPException: Raised when empty address is given
        HTTPException: Raised when invalid output format is given
    """
    address: str
    output_format: str

    @validator("address")
    def check_if_string_is_empty(cls, address):
        if not address:
            raise HTTPException(
                status_code=400, detail="The address string is empty")
        return address

    @validator("output_format")
    def check_if_output_format_is_valid(cls, output_format):
        output_format = output_format.lower()
        allowed_output_format = {"json", "xml"}
        if output_format not in allowed_output_format:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid output format: '{output_format}'. Only allowed formats are {allowed_output_format}")
        return output_format


def construct_response(address: str, output_format: str, response: Response) -> Response:
    """Constructs response in the given format

    Args:
        address (str): Address given to us by the user
        output_format (str): Format in which to send the output. Only "xml", "json" allowed.
        response (Response): Response object gotten from google maps API

    Returns:
        Response: A response object to be sent to the user with the requested response format
    """
    if output_format == "json":
        json_response = response.json()
        json_output = {"address": address,
                       "coordinates": {"lat": "", "long": ""}}
        if json_response["status"] == "OK":
            try:
                # [0] is ok because we are sending only one address at a time
                json_output["coordinates"] = json_response["results"][0]["geometry"]["location"]
            except KeyError as err:
                logging.error(err)
        return JSONResponse(status_code=200, content=json_output, media_type="application/json")
    else:
        xml_response = ET.fromstring(response.text)

        xml_output = ET.Element("root")
        ET.SubElement(xml_output, "address").text = address
        coordinates_element = ET.SubElement(xml_output, "coordinates")
        lat_element = ET.SubElement(coordinates_element, "lat")
        lng_element = ET.SubElement(coordinates_element, "lng")
        lat_element.text = ""
        lng_element.text = ""
        if xml_response.find("status").text == "OK":
            try:
                lat_element.text = xml_response.find("result").find(
                    "geometry").find("location").find("lat").text
                lng_element.text = xml_response.find("result").find(
                    "geometry").find("location").find("lng").text
            except AttributeError as err:
                logging.error(err)
        return Response(content=ET.tostring(xml_output, encoding="UTF-8"), status_code=200,
                        media_type="application/xml")


def get_data_from_google_maps(address: str, output_format: str) -> Response:
    """Gets data from google maps API and handles errors

    Args:
        address (str): The address for which geocoding needs to be done
        output_format (str): Format in which to send the output. Only "xml", "json" allowed.

    Raises:
        HTTPException: Raised when call to google servers fail after multiple retries

    Returns:
        Response : A response object to be sent to the user with the requested response format
    """
    url = f"https://maps.googleapis.com/maps/api/geocode/{output_format}"
    parameters = {"address": address, "key": API_KEY}
    response = session_object.get(url=url, params=parameters)
    try:
        response.raise_for_status()
    except HTTPError:
        logging.error(f"Received error {response.status_code}:{response.text}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    else:
        logging.debug("Response received: {resp.text}")
        return construct_response(address=address, output_format=output_format, response=response)


@app.post("/getAddressDetails")
def get_lat_long_for_address(params: AddressDetailsParameters) -> Response:
    """Function that gets address as input and gives the latitutde, longitude in the requested format

    Args:
        params (AddressDetailsParameters): Request Parameters

    Returns:
        Response : A response object to be sent to the user with the requested response format
    """
    params = params.dict()
    return get_data_from_google_maps(address=params["address"], output_format=params["output_format"])
