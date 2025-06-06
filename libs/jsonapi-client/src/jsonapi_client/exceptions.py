"""
JSON API Python client 
https://github.com/qvantel/jsonapi-client

(see JSON API specification in http://jsonapi.org/)

Copyright (c) 2017, Qvantel
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the Qvantel nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL QVANTEL BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""


class JsonApiClientError(Exception):
    """
    Generic exception class for jsonapi-client
    """
    pass


class ValidationError(JsonApiClientError):
    pass


class DocumentError(JsonApiClientError):
    """
    Raised when 404 or other error takes place.
    Status code is stored in errors['status_code'].
    """
    def __init__(self, *args, errors, **kwargs):
        super().__init__(*args)
        self.errors = errors
        for key, value in kwargs.items():
            setattr(self, key, value)


class DocumentInvalid(JsonApiClientError):
    pass


class AsyncError(JsonApiClientError):
    pass


class NotModifiedError(Exception):
    """Raised when server responds with HTTP 304 Not Modified"""

    pass
