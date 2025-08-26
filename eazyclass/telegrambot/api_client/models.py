models_as_jsonschema = {
    'user': {'properties': {
        'social_id': {'type': ['string', 'null']},
        'platform': {'type': ['string', 'null']},
        'first_name': {'type': ['string', 'null']},
        'last_name': {'type': ['string', 'null']},
        'extra_data': {
                'type': 'object',
                'properties': {
                    'username': {'type': ['string', 'null']},  # Учитываем, что username может быть None
                    'language_code': {'type': ['string', 'null']},
                    'is_premium': {'type': ['boolean', 'null']},
                    'added_to_attachment_menu': {'type': ['boolean', 'null']},
                },
                'additionalProperties': True,  # Разрешаем дополнительные поля, если нужно
            },
        'nonce': {'type': ['string', 'null']},
    }},
}
