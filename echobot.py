"""

Sample bot that echoes back messages.

This is the simplest possible bot and a great place to start if you want to build your own bot.

"""

from __future__ import annotations

from typing import AsyncIterable

import fastapi_poe as fp
from modal import Image, Stub, asgi_app

from vital.client import Vital
from vital.environment import VitalEnvironment


class EchoBot(fp.PoeBot):

    async def get_wearables_data(self):
        client_garmin = Vital(
            api_key="",
            environment=VitalEnvironment.SANDBOX
        )

        client_oura = Vital(
            api_key="",
            environment=VitalEnvironment.SANDBOX
        )

        client_cgm = Vital(
            api_key="",
            environment=VitalEnvironment.SANDBOX
        )

        oura = client_oura.sleep.get(
            user_id="b9f56a91-d0ea-44cc-8729-ce971949275c", 
            start_date="2024-04-06", 
            end_date="2024-04-06"
        )
        sleep_score = oura.sleep[0].score

        cgm = client_cgm.vitals.glucose(
            user_id="40ebd7bd-ebec-4b09-999b-9c01073e266a", 
            start_date="2024-04-06", 
            end_date="2024-04-06"
        )
        cgm_dict = {cgm[point].timestamp: cgm[point].value for point in range(len(cgm))}
        cgm_dict_new = {k:v for k,v in zip(range(300, 300*len(cgm_dict)+1, 300), cgm_dict.values())}

        heart_rate = client_garmin.activity.get_raw(
            user_id="a5c86672-23d8-4772-b4ea-f6906ce7b479", 
            start_date="2024-04-06", 
            end_date="2024-04-06"
        )
        heart_rate_dict = {key: heart_rate.activity[0].data["timeOffsetHeartRateSamples"][key] 
                        for key in heart_rate.activity[0].data["timeOffsetHeartRateSamples"] 
                        if int(key) % 300 == 0}
        
        return {
            "sleep_score": sleep_score,
            "cgm": cgm_dict_new,
            "heart_rate": heart_rate_dict
        }

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(server_bot_dependencies={"Diabotes": 1}, allow_attachments=True)

    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        last_message = request.query[-1].content

        # get data
        wearables_data = await self.get_wearables_data()
        print('wearables_data')
        print(str(wearables_data))

        # call prompt bot
        wearables_prompt = "\nGiven the following health data in the format {’sleep_score’: X/100, ‘cgm’: {timestamp: X mmol/L}, ‘heart_rate’:{timestamp: X bpm}\nData:"
        
        request.query[-1].content += wearables_prompt + str(wearables_data)

        async for msg in fp.stream_request(
            request, "Diabotes", request.access_key
        ):
            yield msg


REQUIREMENTS = ["fastapi-poe==0.0.36", "vital"]
image = Image.debian_slim().pip_install(*REQUIREMENTS)
stub = Stub("echobot-poe")


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    bot = EchoBot()
    # Optionally, provide your Poe access key here:
    # 1. You can go to https://poe.com/create_bot?server=1 to generate an access key.
    # 2. We strongly recommend using a key for a production bot to prevent abuse,
    # but the starter examples disable the key check for convenience.
    # 3. You can also store your access key on modal.com and retrieve it in this function
    # by following the instructions at: https://modal.com/docs/guide/secrets
    # POE_ACCESS_KEY = ""
    # app = make_app(bot, access_key=POE_ACCESS_KEY)
    app = fp.make_app(bot, allow_without_key=True)
    return app
