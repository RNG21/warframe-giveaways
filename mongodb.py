import json
from typing import Union, Dict, Any

import pymongo
from bson.objectid import ObjectId

with open('config.json', encoding='utf-8') as file:
    conn = json.load(file)['connection_string']

cluster = pymongo.MongoClient(conn)
database = cluster['discord']
collection = database['WFG']


def delete(message_id: Union[str, ObjectId]):
    """Deletes a document by _id"""
    return collection.delete_one({'_id': message_id})
delete_giveaway = delete


def truncate():
    """Clears the collection"""
    return collection.delete_many({})


def find(_id: Union[int, str, ObjectId, None], return_cursor=False):
    """

    :param _id: Searches document by _id, returns whole document if _id is None
    :param return_cursor:
    :return:
    """
    if _id is None:
        results = collection.find({})
        return [result for result in results] if return_cursor else results
    return collection.find_one({'_id': _id})
    # return ([result for result in collection.find({})] if return_cursor else collection.find({})) if _id is None else
    # collection.find_one({'_id': _id})


def insert(_id: Union[int, str, ObjectId, dict], dict_: Dict[str, Any] = None):
    if type(_id) == dict:
        return collection.insert_one(_id)
    return collection.insert_one({
        '_id': _id,
        **dict_
    })


def append(_id: int, dict_: Dict[str, Any]):
    return collection.update_one({'_id': _id}, {'$set': dict_})


if __name__ == '__main__':
    import json
    print(json.dumps(find(None, True), indent=4, ensure_ascii=False))
