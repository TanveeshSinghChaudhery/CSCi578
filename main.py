import os
from datetime import datetime

from fastapi import FastAPI, Body, HTTPException, status
from pydantic import BaseModel

import motor.motor_asyncio
from pymongo import ReturnDocument
import requests

from DTO.HistoryModel import GetAllHistory
from models.checkIn import CheckInModel, CheckInCollection
from models.history import HistoryModel

app = FastAPI(
    title="PATROL App API",
    summary="A sample application showing how to use FastAPI For PATROL Application",
)
client = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGODB_URL"])
db = client.college
check_ins_collection = db.get_collection("check_ins")
history_collection = db.get_collection("history")


# Represents an ObjectId field in the database.
# It will be represented as a `str` on the model so that it can be serialized to JSON.


class UpdateCheckInModel(BaseModel):
    lat: float = None
    lng: float = None


@app.post(
    "/checkIn/",
    response_description="Add CheckIn student",
    response_model=CheckInModel,
    status_code=status.HTTP_200_OK,
    response_model_by_alias=False,
)
async def create_check_in(student: CheckInModel = Body(...)):
    new_student = await check_ins_collection.insert_one(
        student.model_dump(by_alias=True, exclude=["id"])
    )
    created_student = await check_ins_collection.find_one(
        {"_id": new_student.inserted_id}
    )
    return created_student


@app.get(
    "/getAllCheckIns/",
    response_description="List all checkIns",
    response_model=CheckInCollection,
    response_model_by_alias=False,
)
async def list_checkins():
    return CheckInCollection(checkIns=await check_ins_collection.find().to_list(1000))


@app.put(
    "/checkIn/{user_id}",
    response_description="Update CheckIn",
    response_model=CheckInModel,
    response_model_by_alias=False,
)
async def update_student(user_id: str, check_in: UpdateCheckInModel = Body(...)):
    check_in = {
        k: v for k, v in check_in.model_dump(by_alias=True).items() if v is not None
    }
    if len(check_in) >= 1:
        update_result = await check_ins_collection.find_one_and_update(
            {"userId": user_id},
            {"$set": check_in},
            return_document=ReturnDocument.AFTER,
        )
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=404, detail=f"checkIn {user_id} not found")

    # The update is empty, but we should still return the matching document:
    if (existing_student := await check_ins_collection.find_one({"user_id": user_id})) is not None:
        return existing_student

    raise HTTPException(status_code=404, detail=f"checkIn {user_id} not found")


@app.get(
    "/getHistory/{start_date}/{end_date}",
    response_description="List history",
    response_model=GetAllHistory,
    response_model_by_alias=False,
)
async def get_all_history(start_date: datetime, end_date: datetime):
    pipeline = [
        {"$match": {"date": {"$gte": start_date, "$lte": end_date}}},
        {"$sort": {"date": 1}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                "latest_record": {"$first": "$$ROOT"}
            }
        },
        {"$replaceRoot": {"newRoot": "$latest_record"}}
    ]
    history_records = await history_collection.aggregate(pipeline).to_list(1000)
    history_records.sort(reverse=True,key=lambda x: x['date'])
    return GetAllHistory(history=[HistoryModel(**record) for record in history_records])


@app.get(
    "/seedAllData",
    response_description="Seed All Data",
    response_model=str,
    response_model_by_alias=False,
)
async def seed_all_data():
    country = 'usa'
    api_url = 'https://api.api-ninjas.com/v1/covid19?country={}'.format(country)
    response = requests.get(api_url, headers={'X-Api-Key': 'HsgNscfZ7JlS48Il0yV0iQ==9E00ixiIbcCpk2Qq'})
    if response.status_code == requests.codes.ok:
        obj = response.json()
        cases = obj[0]['cases']
        history = []
        for date, stats in cases.items():
            total_cases = stats.get('total', 0)
            new_cases = stats.get('new', 0)
            history.append({'date': date, 'total': total_cases, 'new': new_cases})
        inserted_ids = []
        for record in history:
            history_model = HistoryModel(**record)
            result = await history_collection.insert_one(history_model.model_dump(by_alias=True, exclude=["id"]))
            inserted_ids.append(result.inserted_id)
    else:
        print("Error:", response.status_code, response.text)
    return "Seed All data"
