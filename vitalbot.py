"""

Bot to interact with the Vital API to gather user health data from wearables.

"""

from __future__ import annotations
import uuid
import os

from typing import AsyncIterable

import fastapi_poe as fp
from modal import Image, Stub, asgi_app, Secret

from vital.client import Vital
from vital.environment import VitalEnvironment
from vital.core.api_error import ApiError
    
class VitalBot(fp.PoeBot):
    # initialize the vital client
    def __init__(self, api_key: str, environment: VitalEnvironment=VitalEnvironment.SANDBOX):
        self.client = Vital(
            api_key=api_key,
            environment=environment
        )

    async def get_wearables_data(self, vital_user_id: str):
        # client_garmin = Vital(
        #     api_key="",
        #     environment=VitalEnvironment.SANDBOX
        # )

        # client_oura = Vital(
        #     api_key=,
        #     environment=VitalEnvironment.SANDBOX
        # )

        # client_cgm = Vital(
        #     api_key="",
        #     environment=VitalEnvironment.SANDBOX
        # )

        oura = self.client.sleep.get(
            user_id=vital_user_id, 
            start_date="2024-04-19", 
            end_date="2024-04-20",
        )
        print(oura)
        sleep_score = oura.sleep[0].score

        # cgm = client_cgm.vitals.glucose(
        #     user_id="40ebd7bd-ebec-4b09-999b-9c01073e266a", 
        #     start_date="2024-04-06", 
        #     end_date="2024-04-06"
        # )
        # cgm_dict = {cgm[point].timestamp: cgm[point].value for point in range(len(cgm))}
        # cgm_dict_new = {k:v for k,v in zip(range(300, 300*len(cgm_dict)+1, 300), cgm_dict.values())}

        # heart_rate = client_garmin.activity.get_raw(
        #     user_id="a5c86672-23d8-4772-b4ea-f6906ce7b479", 
        #     start_date="2024-04-06", 
        #     end_date="2024-04-06"
        # )
        # heart_rate_dict = {key: heart_rate.activity[0].data["timeOffsetHeartRateSamples"][key] 
        #                 for key in heart_rate.activity[0].data["timeOffsetHeartRateSamples"] 
        #                 if int(key) % 300 == 0}
        
        return {
            "sleep_score": sleep_score,
            # "cgm": cgm_dict_new,
            # "heart_rate": heart_rate_dict
        }

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(server_bot_dependencies={"Diabotes": 1}, allow_attachments=True)
    
    async def get_vital_user(self, client_user_id: str) -> str:
        # try to get the user from vital
        vital_user_id = self.client.user.get_by_client_user_id(client_user_id)
        
        return vital_user_id
        
    async def create_user(self, client_user_id: str) -> str:
        # create the user
        user_data = self.client.user.create(client_user_id=client_user_id)
        vital_user_id = user_data.user_id
    
        # generate token link for user to register devices
        token_link = self.client.link.token(user_id=vital_user_id)
        # format the returned token with the base url
        token_link = f"https://link.tryvital.io/?token={token_link.link_token}&env=sandbox&region=us"
        return token_link

    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        last_message = request.query[-1].content
        print(request)
        # define blank vital user id
        vital_user_id = None
        
        try:
            vital_user_id = await self.get_vital_user(request.user_id)
        except ApiError as e:
            if e.status_code == 404:
                vital_user_id = None
            
        
        if vital_user_id is None:
            token_link = await self.create_user(request.user_id)
            sign_up_prompt = f"Diabotes is excited to help you with your health! Please open this link to register your wearables: {token_link}"

            yield fp.PartialResponse(text=sign_up_prompt)
            
        else:
            wearables_data = await self.get_wearables_data(vital_user_id)
            # call prompt bot
            wearables_prompt = "\nGiven the following health data in the format {’sleep_score’: X/100, ‘cgm’: {timestamp: X mmol/L}, ‘heart_rate’:{timestamp: X bpm}\nData:"
            
            request.query[-1].content += wearables_prompt + str(wearables_data)

            async for msg in fp.stream_request(
                request, "Diabotes", request.access_key
            ):
                yield msg


REQUIREMENTS = ["fastapi-poe==0.0.36", "vital"]
image = Image.debian_slim().pip_install(*REQUIREMENTS)
stub = Stub("vitalbot-poe")


@stub.function(image=image, secrets=[Secret.from_name("vital-api-key")])
@asgi_app()
def fastapi_app():
    bot = VitalBot(os.environ["VITAL_API_KEY"])
    # Optionally, provide your Poe access key here:
    # 1. You can go to https://poe.com/create_bot?server=1 to generate an access key.
    # 2. We strongly recommend using a key for a production bot to prevent abuse,
    # but the starter examples disable the key check for convenience.
    # 3. You can also store your access key on modal.com and retrieve it in this function
    # by following the instructions at: https://modal.com/docs/guide/secrets
    # POE_ACCESS_KEY = ""
    # app = make_app(bot, access_key=POE_ACCESS_KEY)
    app = fp.make_app(bot, allow_without_key=True)
    app.get("/health")(lambda: {"message": "Welcome to the VitalBot!"})
    app.post("/create_user")(bot.create_user)
    app.get("/wearables_data/{vital_user_id}")(bot.get_wearables_data)
    return app
