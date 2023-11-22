# ESTY V3 API: Connection to Etsy using API V3

import copy
import io
from math import prod
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytz
import requests
from PIL import Image
from PIL import ImageFile

from datasync.libs.errors import Errors
from datasync.libs.response import Response
from datasync.libs.tracking_company import TrackingCompany
from datasync.libs.utils import *
from datasync.models.channel import ModelChannel
from datasync.models.constructs.category import CatalogCategory
from datasync.models.constructs.order import Order, OrderProducts, OrderItemOption, OrderHistory, OrderAddress, OrderAddressCountry
from datasync.models.constructs.product import Product, ProductImage, ProductAttribute, ProductVariant, \
    ProductVariantAttribute, ProductVideo, ProductLocation
import dateutil.relativedelta

class ModelChannelsEtsyV3(ModelChannel):
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
    PRODUCT_STATUS = ['active', 'inactive', 'draft', 'expired', 'sold_out']
    
    def __init__(self):
        super().__init__()
        self._api_url = None
        self._version_api = None
        self._collection_type = None
        self._shopify_countries = None
        self._location_id = None
        self._last_product_response = None
        self._last_images = None
        self._flag_finish_product = False
        self._flag_finish_order = False
        self._product_next_link = False
        self._order_next_link = False
        self._order_max_last_modified = False
        self._metafields_definitions = False
        self._sale_channel_id = None
        self._file_log = None
        self._last_status = None
        self._last_product_created_at = None
        self._last_order_created_at = None
        self._api_version = ''
        self._brands = {}
        self._query_string_auth = None
        self._zero_tax = None
        self._weight_units = False
        self._dimension_units = False
        self._store_information = False
        self._pull_custom = False
        self._attributes = dict()
        self._all_attributes = dict()
        self._flag_finish_category = False
        self._category_next_page = 1
        self._product_images = {}
        self._product_pull_type = "publish"
        self._category_id = None

    def create_api_url(self):
        api_url = f"{get_config_ini('etsyv3', 'api_url')}"
        return api_url

    def _checkToken(self,token):
        if token and token != 'false' or token != 'False':
            path = f'/application/shops/{self._state.channel.config.api.shop_id}/listings'
            method = 'GET'
            header = {
                'Authorization': f'Bearer {token}',
                'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                'limit': '1',
                }
            url = f"{self._api_url}/{path}"
            res = requests.request(method, url, headers=header)
            if res.status_code == 200 or 'access token is expired' not in res.text:
                return True
            else:
                return False
        return False

    def get_max_last_modified_product(self):
        if self._state.pull.process.products.last_modified:
            if to_str(self._state.pull.process.products.last_modified).isnumeric():
                return convert_format_time(self._state.pull.process.products.last_modified, new_format = "%Y-%m-%dT%H:%M:%S+07:00")
            return self._state.pull.process.products.last_modified
        return False

    def getAuthAccessToken(self):
        if self._checkToken(self._state.channel.config.api.access_token):
            return self._state.channel.config.api.access_token
        else:
            if self._state.channel.config.api.access_token_secret:
                path = '/public/oauth/token'
                method = 'POST'
                data = f"grant_type=refresh_token&refresh_token={self._state.channel.config.api.access_token_secret}&client_id={self._state.channel.config.api.consumer_key}"
                header = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
                
                res = requests.request(method=method, url=f"{self._api_url}{path}", headers=header, data=data)
                print(res,res.text)
                if res.status_code == 200:
                    data = res.json()
                    self._state.channel.config.api.access_token = data['access_token']
                    self._state.channel.config.api.access_token_secret = data['refresh_token']
                    return self._state.channel.config.api.access_token
                else:
                    return False
            else:
                return False

    def api(self, method, extpath, data=None, headers=None, files=None):
        if not self._api_url:
            self._api_url = self.create_api_url()
        if not extpath.startswith('/'):
            extpath = '/' + extpath
        if self._api_url.endswith('/') and extpath.startswith('/'):
            extpath = extpath[1:]
        url = f"{self._api_url}{extpath}"
        if not headers:
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                'Authorization': f'Bearer {self.getAuthAccessToken()}'
            }
        if not headers['x-api-key'] or headers['Authorization']:
            headers = {
                'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                'Authorization': f'Bearer {self.getAuthAccessToken()}'
            }
        res = self.requests(url=url, method=method, headers=headers, data=data, files=files)
        retry = 0
        print(f"\nbbbbbbbbb{res}\n")
        while res.status_code == 429 and retry < 3:
            retry += 1
            time.sleep(5)
            res = self.requests(url=url, method=method, headers=headers, data=data, files=files)
        return res

    def requests(self, url, method = 'get', headers=None, data=None, files=None):
        method = to_str(method).lower()
        if not headers:
            headers = {}
            headers['User-Agent'] = get_random_useragent()
        elif isinstance(headers, dict) and 'User-Agent' not in headers:
            headers['User-Agent'] = get_random_useragent()
        headers['Accept'] = 'application/json'
        
        response = False
        request_options = {
            'headers': headers,
            'timeout': 60,
            'verify': False,
        }
        if files:
            request_options['files'] = files
            request_options['data'] = data
        else:
            if method == 'get':
                request_options['params'] = data
            elif method in ['post', 'put', 'patch']:
                request_options['json'] = data
                if 'Content-Type' not in headers:
                    headers['Content-Type'] = 'application/json'
        request_options = self.combine_request_options(request_options)
        print(f"aaaaaaaaaaaaaaaaaaaaaaaaaaa{url}\n{headers}")
        response_data = False
        try:
            response = requests.request(method, url, **request_options)
            self._last_header = response.headers
            self._last_status = response.status_code
            response_data = json_decode(response.text)
            print(f"aaaaaaaaaaaaaaaaaaaaaaaaaaa{response_data}\n")
            if response_data:
                try:
                    response_prodict = Prodict(**response_data)
                except Exception:
                    response_prodict = response_data
                response_data = response_prodict
            if response.headers.get('X-Remaining-Today') and response.headers.get('X-Remaining-This-Second'):
                req_remain_today = response.headers.get('X-Remaining-Today')
                request_remain = response.headers.get('X-Remaining-This-Second')
                if to_int(request_remain) < 5:
                    time.sleep(1)
                if to_int(req_remain_today) < 10:
                    now = datetime.now()
                    now = now.replace(tzinfo=pytz.utc)
                    now = now.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
                    end_day = now.replace(hour=23, minute=59, second=59)
                    time_sleep = (end_day - now).total_seconds()
                    time.sleep(time_sleep)
            else:
                time.sleep(1)

            def log_request_error(_log_type = 'request'):
                if not _log_type:
                    _log_type = 'request'
                error = {
                    'method': method,
                    'status': response.status_code,
                    'data': to_str(data),
                    'header': to_str(response.headers),
                    'response': response.text,
                }
                self.log_request_error(url, log_type = _log_type ,**error)

            if response.status_code == 401:
                if response_data.errors and 'Invalid' in to_str(response_data.errors):
                    log_request_error()
                    self.notify(Errors.ETSY_API_AUTH_INVALID)
                    headers['Authorization'] = f'Bearer {self.getAuthAccessToken()}'
                    return self.requests(url, headers, data, method)
            if response.status_code > 201 or self.is_log():
                log_request_error(self._file_log)
        except Exception as e:
            self.log_traceback()
        return response_data

    def check_response_import(self, response, convert, entity_type = ''):
        entity_id = convert.id if convert.id else convert.code
        if not response:
            return Response().error()
        elif response and hasattr(response, 'errors') and response.errors:
            console = list()
            if isinstance(response.errors, list):
                for error in response.errors:
                    if isinstance(error, list):
                        error_messages = ' '.join(error)
                    else:
                        error_messages = error
                    console.append(error_messages)
            if isinstance(response.errors, dict) or isinstance(response.errors, Prodict):
                for key, error in response['errors'].items():
                    if isinstance(error, list):
                        error_messages = ' '.join(error)
                    else:
                        error_messages = error
                    console.append(key + ': ' + error_messages)
            else:
                console.append(response['errors'])
            msg_errors = '_lic_nl_'.join(console)
            self.log(entity_type + ' id ' + to_str(entity_id) + ' import failed. Error: ' + msg_errors,
                     "{}_errors".format(entity_type))
            return Response().error(msg = msg_errors)

        else:
            return Response().success()

    def display_pull_channel(self):
        parent = super().display_pull_channel()
        if parent.result != Response().SUCCESS:
            return parent
        if self.is_product_process():
            params = {}
            self._state.pull.process.products.error = 0
            self._state.pull.process.products.imported = 0
            self._state.pull.process.products.new_entity = 0
            params['limit'] = self._request_data.get('limit', 25)
            params['offset'] = self._request_data.get('offset', 0)
            if self._request_data.get('include_filters'):
                for k,v in self._request_data.get('include_filters').items():
                    if k in ["Shipping","Images","Shop","User","Translations","Inventory","Videos"]:
                        params['includes'] += f",{k}"
            if self.is_refresh_process():
                params['offset'] = 0
                params['limit'] = self._state.pull.process.products.total
                last_modified = self.get_max_last_modified_product()
                if last_modified:
                    params['last_modified'] = last_modified
            else:
                if self._state.pull.process.products.total > 0:
                    params['offset'] = self._state.pull.process.products.total
                for type in self.PRODUCT_STATUS:
                    params['state'] = type
                    products = self.pull_products(params)
                    if products:
                        self._state.pull.process.products.total += products.count()
                        if self._state.pull.process.products.total > params['limit']:
                            params['offset'] = params['limit']
                            params['limit'] = self._state.pull.process.products.total - params['limit']
                        products = self.pull_products(params)

    def pull_products(self, params):
        if not self._api_url:
            self._api_url = self.create_api_url()
        url = f"{self._api_url}/application/shops/{self._state.channel.config.api.shop_id}/listings"
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': f'{self._state.channel.config.api.consumer_key}',
            'Authorization': f'Bearer {self.getAuthAccessToken()}'
        }
        res = self.requests(url, 'GET', headers, params)
        if res.status_code == 200:
            return res.data
        return False

    def convert_to_etsy_product(self, convert, product, products_ext):
        if not product.name:
            return Response().error(Errors.PRODUCT_DATA_INVALID, 'Product name is empty')
        product_data = {
            'title': product.get('name'),
            'price': product.get('price'),
            'quantity': product.get('qty'),
            'state': product.get('status'),
            'taxonomy_id': product.template_data.category.category.id,
            'who_made': product.template_data.category.about.who_made,
            'is_supply': bool(int(product.template_data.category.about.is_supply)),
            'when_made': product.template_data.category.about.when_made,
            'shipping_profile_id': product.template_data.shipping.shipping_id,
            'return_policy_id': product.template_data.shipping.return_id,
            'materials': product.materials or product.template_data.category.advance.materials,
            'shop_section_id': product.template_data.category.advance.section,
            'processing_min': 7,
            'processing_max': 14,
            'styles': '',
            'item_weight_unit': product.weight_units,
            'item_dimensions_unit': product.dimension_units,
            'production_partner_ids': product.template_data.category.about.production_partner_ids,
        }
        if product.weight:
            product_data['item_weight'] = product.weight
        if product.length:
            product_data['item_length'] = product.length
        if product.width:
            product_data['item_width'] = product.width
        if product.height:
            product_data['item_height'] = product.height
        if product.template_data.personalization:
            product_data.update({
                'is_personalizable': True if product.template_data.personalization.status == 'enabled' else False,
                'personalization_is_required': product.template_data.personalization.is_required,
                'personalization_char_count_max': product.template_data.personalization.char_count_max,
                'personalization_instructions': product.template_data.personalization.instructions,
            })
        if product.template_data.category.advance.tags:
            product_data['tags'] = product.template_data.category.advance.tags
        if product.description:
            # if product.description is html format, convert to plain text because etsy not support html description
            product_data['description'] = html_unescape(product.description)
        images = list()
        if product.images:
            for image in product.images:
                if image.url:
                    images.append({
                        'image': image.url,
                        'rank': image.position or 1,
                        'overwrite': True,
                        'alt_text': image.label or '',
                    })
        return Response().success((product_data,images))

    def set_last_product_response(self, response, images):
        self._last_product_response = response
        self._last_images = images

    def get_last_product_response(self):
        return self._last_product_response, self._last_images

    def product_import(self, convert: Product, product, products_ext):
        converted_product = self.convert_to_etsy_product(convert, product, products_ext)
        if not converted_product:
            return converted_product
        productcv, images = converted_product.data
        res = self.api(method='POST', extpath=f'/application/shops/{self._state.channel.config.api.shop_id}/listings', data=productcv)
        check_res = self.check_response_import(res, product, 'product')
        if check_res.result != Response().SUCCESS:
            return check_res
        product_id = res.listing_id
        self._state.pull.process.products.imported += 1
        self.set_last_product_response(res, images)
        if product.variants:
            qty = 0
            for variant in product.variants:
                qty += variant.qty
            if qty > 0 and not product.is_in_stock:
                self._extend_product_map['is_in_stock'] = True
        return Response().success(product_id)

    def after_product_import(self, product_id, convert, product, products_ext):
        eemap = copy.deepcopy(self._extend_product_map)
        self._extend_product_map = {}
        lastrep, images = self.get_last_product_response()
        if not lastrep:
            return Response().error()
        if images:
            for image in images:
                if image['image']:
                    # download image and post to etsy
                    img = urlopen(image['image']).read()
                    if img[1:4] == b'PNG':
                        process = Image.open(io.BytesIO(img)).convert('RGBA')
                        new_img = Image.new("RGBA", process.size, "WHITE")
                        new_img.paste(process, mask=process)
                        process = new_img.convert('RGB')
                        img = io.BytesIO()
                        process.save(img, format='JPEG')
                        img = img.getvalue()
                    if img:
                        image.pop('image')
                        headers = {
                            'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                            'Authorization': f'Bearer {self.getAuthAccessToken()}'
                        }
                        payload = {
                            'rank': image['rank'],
                            'overwrite': True,
                            'alt_text': image['alt_text'],
                        }
                        files = [('image', img)]
                        res = self.api(method='POST', extpath=f'/application/shops/{self._state.channel.config.api.shop_id}/listings/{product_id}/images', headers=headers, files=files, data=payload)
                        if not res.errors:
                            image['id'] = res.listing_image_id
                        else:
                            return Response().error()
                    else:
                        continue
                else:
                    continue
        if product.template_data.advance:
            get_properties_path = f'/application/seller-taxonomy/nodes/{product.template_data.category.category.id}/properties'
            properties = self.api(method='GET', extpath=get_properties_path)
            find_by_key = lambda l,k,v: next((i for i in l if i[k] == v), None)
            get_number_from_string = lambda s: ''.join([i for i in s if i.isdigit()])
            if properties:
                for attribute in product.template_data.advance.attributes:
                    property_data = find_by_key(properties, 'property_id', attribute.attribute_id)
                    if not property_data:
                        continue
                    if attribute.attribute_value:
                        property_name = find_by_key(property_data["possible_values"],"value_id",int(attribute.attribute_value))["name"]
                        value_ids = []
                        values = []
                        value_ids.append(attribute.attribute_value)
                        values.append(property_name)
                        payload=urlencode({'value_ids': ', '.join(str(x) for x in value_ids).replace(" ","")}, doseq = False) + '&' + urlencode({'values': ', '.join(values)}, doseq=False)
                        path = f"/application/shops/{self._state.channel.config.api.shop_id}/listings/{product_id}/properties/{attribute.attribute_id}"
                        headers = {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }
                        self.api(method="PUT",extpath=path,headers=headers,data=payload)
        if product.variants:
            inventory_variants = list()
            for variant in product.variants:
                list_variant_name = [ _.attribute_name for _ in variant.attributes] 
                list_variant_value_name = [ _.attribute_value_name for _ in variant.attributes]
                variant_request_data = {
                    "sku": product.sku,
                    "property_values": [
                        {
                        "property_id": 513,
                        "value_ids": [

                        ],
                        "property_name": list_variant_name[0],
                        "values": [
                            list_variant_value_name[0],
                        ]
                        },
                        {
                        "property_id": 514,
                        "value_ids": [
                            
                        ],
                        # "property_name": variant.attributes[1].attribute_name +"-"+ variant.attributes[2].attribute_name,
                        "property_name": ('-').join(list_variant_name[1:]),
                        "values": [
                            ('-').join(list_variant_value_name[1:]),
                        ]
                        }
                    ],
                    "offerings": [
                        {
                        "price": variant.price,
                        "quantity": variant.qty if variant.qty else 1,
                        "is_enabled": variant.visible
                        }
                    ]
                }
                inventory_variants.append(variant_request_data)
            payload = {
                'products':inventory_variants
            }
            path=f"/application/listings/{product_id}/inventory"
            self.api(method="PUT",extpath=path,data=payload)
        self._extend_product_map = copy.deepcopy(eemap)
        return Response ().success()
