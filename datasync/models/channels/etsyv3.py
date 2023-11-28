# ESTY V3 API: Connection to Etsy using API V3

import copy
import io
from math import prod
from unicodedata import category
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from numpy import product

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
from datasync.models.constructs.order import Order, OrderProducts, OrderItemOption, OrderHistory, OrderAddress, \
    OrderAddressCountry
from datasync.models.constructs.product import Product, ProductImage, ProductAttribute, ProductVariant, \
    ProductVariantAttribute, ProductVideo, ProductLocation
import dateutil.relativedelta

class ModelChannelsEtsyV3(ModelChannel):
    USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/80.0.3987.149 Safari/537.36")
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

    @staticmethod
    def create_api_url():
        api_url = f"{get_config_ini('etsyv3', 'api_url')}"
        return api_url

    def _check_token(self, token):
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
                return convert_format_time(self._state.pull.process.products.last_modified,
                                           new_format="%Y-%m-%dT%H:%M:%S+07:00")
            return self._state.pull.process.products.last_modified
        return False

    def get_auth_access_token(self):
        if self._check_token(self._state.channel.config.api.access_token):
            return self._state.channel.config.api.access_token
        else:
            if self._state.channel.config.api.access_token_secret:
                path = '/public/oauth/token'
                method = 'POST'
                data = f"grant_type=refresh_token&refresh_token={self._state.channel.config.api.access_token_secret}\
                        &client_id={self._state.channel.config.api.consumer_key}"
                header = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                }

                res = requests.request(method=method, url=f"{self._api_url}{path}", headers=header, data=data)
                print(res, res.text)
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
                'Authorization': f'Bearer {self.get_auth_access_token()}'
            }
        if not headers.get('x-api-key') or headers.get('Authorization'):
            headers = {
                'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                'Authorization': f'Bearer {self.get_auth_access_token()}'
            }
        res = self.requests(url=url, method=method, headers=headers, data=data, files=files)
        return res

    def requests(self, url, method='get', headers=None, data=None, files=None):
        method = to_str(method).lower()
        if not headers:
            headers = {'User-Agent': get_random_useragent()}
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

            def log_request_error(_log_type='request'):
                if not _log_type:
                    _log_type = 'request'
                error = {
                    'method': method,
                    'status': response.status_code,
                    'data': to_str(data),
                    'header': to_str(response.headers),
                    'response': response.text,
                }
                self.log_request_error(url, log_type=_log_type, **error)

            if response.status_code == 401:
                if response_data.errors and 'Invalid' in to_str(response_data.errors):
                    log_request_error()
                    self.notify(Errors.ETSY_API_AUTH_INVALID)
                    headers['Authorization'] = f'Bearer {self.get_auth_access_token()}'
                    return self.requests(url, headers, data, method)
            if response.status_code > 201 or self.is_log():
                log_request_error(self._file_log)
        except Exception as e:
            self.log_traceback()
            return False
        return response_data

    def check_response_import(self, response, convert, entity_type=''):
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
            return Response().error(msg=msg_errors)

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
            self._state.pull.process.products.total=0
            params['limit'] = self._request_data.get('limit', 25)
            params['offset'] = self._request_data.get('offset', 0)
            params['includes'] = "Shipping,Images,Shop,User,Translations,Inventory,Videos"
            if self.is_refresh_process():
                params['offset'] = 0
                params['limit'] = self._state.pull.process.setting.products or 25
                self._state.pull.process.products.id_src = 0
            else:
                params['offset'] = self._state.pull.process.products.id_src or 0
            statuses = ['active']
            if self._request_data.get('import_all'):
                statuses = self.PRODUCT_STATUS
            else:
                statuses += [status for status in self.PRODUCT_STATUS if self._request_data.get(f'include_{status}')]
            for status in statuses:
                params['state'] = status
                products = self.pull_products(params)
                if products and products.count > 0:
                    self._state.pull.process.products.total += products.count
        if self.is_order_process():
            self._state.pull.process.orders.total = 0
            self._state.pull.process.orders.imported = 0
            self._state.pull.process.orders.new_entity = 0
            self._state.pull.process.orders.error = 0
            self._state.pull.process.orders.id_src = 0
            order_api = self.api(f"/application/shops/{self._state.channel.config.api.shop_id}/receipts")
            self._state.pull.process.orders.total = json.loads(order_api)["count"]

        if self.is_category_process():
            self._state.pull.process.categories.total = 0
            self._state.pull.process.categories.imported = 0
            self._state.pull.process.categories.new_entity = 0
            self._state.pull.process.categories.error = 0
            self._state.pull.process.categories.total = 1
        return Response().success()

    def pull_products(self, params):
        if not self._api_url:
            self._api_url = self.create_api_url()
        #convert params to query string
        query_string = urlencode(params) if params else ''
        url = f"{self._api_url}/application/shops/{self._state.channel.config.api.shop_id}/listings?{query_string}"
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': f'{self._state.channel.config.api.consumer_key}',
            'Authorization': f'Bearer {self.get_auth_access_token()}'
        }
        res = self.requests(url, 'GET', headers)
        if self._last_status == 200:
            return res
        return False

    def get_product_by_id(self, product_id):
        includes= "Shipping,Images,Shop,User,Translations,Inventory,Videos"
        product = self.api(method='GET', extpath=f'/application/listings/batch?listing_ids={product_id}&includes={includes}')
        if self._last_status == 404:
            return Response().create_response(result=Response().ERROR, msg='Product not found')
        if not product or not product.results:
            return Response().error()
        return Response().success(data=product.results[0])
    
    def get_product_id_import(self, convert: Product, product, products_ext):
        return product.listing_id
    
    def get_products_main_export(self):
        if self._flag_finish_product:
            return Response().finish()
        params = dict()
        products = list()
        limit_data = 2
        params = {
            'limit': limit_data,
             
        }
        if self._product_next_link:
            params['offset'] = self._state.pull.process.products.imported
        else:
            params['offset'] = self._state.pull.process.products.imported or 0
        params['includes'] = "Shipping,Images,Shop,User,Translations,Inventory,Videos"
        statuses = ['active']
        if self._request_data.get('import_all'):
            statuses = self.PRODUCT_STATUS
        else:
            statuses += [ status for status in self.PRODUCT_STATUS if self._request_data.get(f'include_{status}')]
        for status in statuses:
            params['state'] = status
            products_req = self.pull_products(params)
            if not products_req:
                return Response().error()
            if products_req.count == 0 or len(products_req.results) == 0:
                continue
            # if len(products_req.results) < limit_data:
            #     self._flag_finish_product = True
            products += products_req.results
        if len(products) == 0 or not products:
            return Response().finish()
        if self._state.pull.process.products.total >= self._state.pull.process.products.imported:
            self._product_next_link = True
        else:
            self._flag_finish_product = True
        return Response().success(data = products)

    def get_products_ext_export(self, products):
        if not products:
            return Response().error(Errors.ETSY_GET_PRODUCT_FAILED, 'Get product failed')
        extend = Prodict()
        for product in products:
            product_id = to_str(product.listing_id)
            extend[to_str(product_id)] = product
        return Response().success(extend)

    def check_product_import(self, product_id, convert: Product):
        path = f"/application/shops/{self._state.channel.config.api.shop_id}/listings"
        product_list = self.api(method='GET', extpath=path).results
        key_to_find = "sku"
        value_to_find = convert.sku
        result = [item for item in product_list if item.get(key_to_find) == value_to_find]
        if len(result) == 0:
            return False
        else:
            return str(result[0]["id"])

    def get_taxonomies_name(self, taxonomies_id):
        taxonomies= self.api(method='GET', extpath=f'/application/seller-taxonomy/nodes')
        if not taxonomies:
            return False
        taxonomies = taxonomies.results
        product_taxonomies = next((item for item in taxonomies if item['id'] == taxonomies_id), None)
        if not product_taxonomies:
            return False
        else:
            # preverse to parent taxonomies for full path name
            mame_path_ids = sorted(product_taxonomies['full_path_taxonomy_ids'])
            # Create name path as format root > child > ... > current
            name_path = ' > '.join([next((item for item in taxonomies if item['id'] == id), None)['name'] for id in mame_path_ids])
            return name_path
    
    def _convert_product_export(self, product, products_ext: Prodict):
        product_id = f'{product.listing_id}'
        product_data = Product()
        product_data.tags = (', ').join(product.tags)
        product_data.id = product_id
        product_data.is_variant = False
        product_data.sku = product.skus[0] if len(product.skus) > 0 else ''
        product_data.skus = product.skus
        product_data.name = product.title
        product_data.price = product.price.amount
        product_data.cost = product.price.amount
        product_data.status = product.state
        product_data.qty = product.quantity
        product_data.weight = product.weight
        product_data.length = product.length
        product_data.width = product.width
        product_data.height = product.height
        product_data.length = product.length
        product_data.width = product.width
        product_data.height = product.height
        product_data.weight_units = product.item_weight_unit
        product_data.dimension_units = product.item_dimensions_unit
        product_data.description = product.description
        product_data.created_at = product.creation_tsz
        product_data.updated_at = product.last_modified_tsz
        product_data.visibility = product.state
        product_data.is_in_stock = True if product.quantity > 0 else False
        product_data.manage_stock = True
        product_data.is_salable = True
        product_data.type = 'simple'
        product_data.url_key = product.listing_id
        product_data.url_path = product.url
        product_data.brand = product.brand
        if product.images and len(product.images) > 0:
            for image in product.images:
                if image.url_fullxfull:
                    product_data.images.append(ProductImage().from_dict({
                        'url': image.url_fullxfull,
                        'position': image.rank,
                        'label': image.alt_text,
                        'image_id': image.listing_image_id,
                    }))
        
        if product.inventory and product.inventory.products:
            # product.inventory.products is variants in with contruct of etsy
            for variant in product.inventory.products:
                variant_data = ProductVariant()
                variant_data.id = variant.product_id
                variant_data.sku = variant.sku
                variant_data.qty = product.quantity
                variant_data.price = variant.offerings[0].price.amount
                variant_data.cost = variant.offerings[0].price.amount
                variant_data.is_salable = True
                variant_data.is_in_stock = True if variant.offerings[0].quantity > 0 else False
                variant_data.visibility = True if variant.offerings[0].is_enabled else False
                variant_data.created_at = product.creation_tsz
                variant_data.updated_at = product.last_modified_tsz
                variant_data.images = product_data.images
                variant_data.attributes = []
                variant_data.parent_id = product_id
                if not variant.property_values:
                    continue
                else:
                    for p in variant.property_values:
                        if isinstance(p.get('value_ids'), list) and isinstance(p.get('values'), list) and len(p.get('value_ids')) > 0:
                            variant_data.attributes.append(ProductVariantAttribute().from_dict({
                                'attribute_id': p.get('property_id'),
                                'attribute_name': p.get('property_name'),
                                'attribute_value_id': p.get('value_ids')[0],
                                'attribute_value_name': p.get('values')[0],
                            }))
                            product_data.attributes.append(ProductAttribute().from_dict({
                                'attribute_id': p.get('property_id'),
                                'attribute_name': p.get('property_name'),
                                'attribute_value_id': p.get('value_ids')[0],
                                'attribute_value_name': p.get('values')[0],
                            }))
                product_data.variants.append(variant_data)
        # extend data: Template_data
        product_data.template_data = Prodict()
        product_data.template_data.category = {
            "about": {
                'who_made': product.who_made,
                'is_supply': product.is_supply,
                'when_made': product.when_made,
                'production_partner_ids': product.production_partners,
            },
            "category": {
                'id': product.taxonomy_id,
                'name': self.get_taxonomies_name(product.taxonomy_id),
            },
            "advance": {
                'materials': product.materials,
                'tags': (',').join(product.tags),
                'section': product.shop_section_id,
            },
            "attributes": [],
        }
        product_data.template_data.shipping = {
            "shipping_id": product.shipping_profile_id,
            "policy_id": product.return_policy_id,
        }
        if product.is_personalizable:
            product_data.template_data.personalization = {
                'status': 'enabled',
                'is_required': product.personalization_is_required,
                'char_count_max': product.personalization_char_count_max,
                'instructions': product.personalization_instructions,
            }
        return Response().success(data=product_data)

    @staticmethod
    def convert_to_etsy_product(convert, product, products_ext):
        if not product.name:
            return Response().error(Errors.PRODUCT_DATA_INVALID, 'Product name is empty')
        product_data = {
            'title': product.get('name'),
            'price': product.get('price') if to_int(product.get('price')) < 50000 else 500,
            'quantity': 10,
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
        return Response().success((product_data, images))

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
        res = self.api(method='POST', extpath=f'/application/shops/{self._state.channel.config.api.shop_id}/listings',
                       data=productcv)
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
                    try:
                        img = urlopen(image['image']).read()
                        if img[1:4] == b'PNG':
                            process = Image.open(io.BytesIO(img)).convert('RGBA')
                            new_img = Image.new("RGBA", process.size, "WHITE")
                            new_img.paste(process, mask=process)
                            process = new_img.convert('RGB')
                            img = io.BytesIO()
                            process.save(img, format='JPEG')
                            img = img.getvalue()
                    except Exception as e:
                        img = None
                        continue
                    if img:
                        image.pop('image')
                        headers = {
                            'x-api-key': f'{self._state.channel.config.api.consumer_key}',
                            'Authorization': f'Bearer {self.get_auth_access_token()}'
                        }
                        payload = {
                            'rank': image['rank'],
                            'overwrite': True,
                            'alt_text': image['alt_text'],
                        }
                        files = [('image', img)]
                        path = f'/application/shops/{self._state.channel.config.api.shop_id}/listings/{product_id}/images'
                        res = self.api(method='POST',
                                       extpath=path,
                                       headers=headers, files=files, data=payload)
                        if not res.errors:
                            image['id'] = res.listing_image_id
                            print("PUSH IMAGE DONE")
                        else:
                            return Response().error()
                    else:
                        continue
                else:
                    continue
        path = f'/application/seller-taxonomy/nodes/{lastrep.taxonomy_id}/properties'
        properties = self.api(method='GET', extpath=path)
        if not properties:
            return Response().error()
        properties = properties.results
        def find_by_key(list_dict, key, value):
            list_key = key.split(',')
            if isinstance(list_key,list):
                for k in list_key:
                    data = next((item for item in list_dict if item[k] == value), None)
                    return data if data else False
        if product.template_data.category.advance:
            print("PUSH PROPERTY")
            if properties:
                for attribute in product.template_data.category.advance.attributes:
                    payload = {}
                    possible_propeties_values = find_by_key(properties, 'property_id', attribute.attribute_id)
                    if not possible_propeties_values:
                        continue
                    possible_propeties_values = possible_propeties_values['possible_values']
                    if attribute.attribute_value:
                        property_name = find_by_key(possible_propeties_values, "value_id", int(attribute.attribute_value))["name"]
                        payload = {
                            'value_ids': [attribute.attribute_value],
                            'values': [property_name],
                        }
                    path = f"/application/shops/{self._state.channel.config.api.shop_id}/listings/{product_id}/properties/{attribute.attribute_id}"
                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }
                    self.api(method="PUT", extpath=path, headers=headers, data=payload)
                print("PUSH PROPERTY DONE")
        if product.variants:
            print("PUSH VARIANT")
            inventory_variants = list()
            for variant in product.variants:
                list_variant_attribute = [_.attribute_name for _ in variant.attributes]
                list_variant_attribute_value = [_.attribute_value_name for _ in variant.attributes]
                if len(list_variant_attribute) >= 2:
                    # if property not exist in etsy, create new property and push variant property_id: 513, 514
                    variant_request_data = {
                        "sku": product.sku,
                        "property_values": [
                            {
                                "property_id": 513,
                                "value_ids": [
                                ],
                                "property_name": list_variant_attribute[0],
                                "values": [
                                    list_variant_attribute_value[0],
                                ]
                            },
                            {
                                "property_id": 514,
                                "value_ids": [
                                ],
                                "property_name": ('-').join(list_variant_attribute[1:]),
                                "values": [
                                    ('-').join(list_variant_attribute_value[1:]),
                                ]
                            },
                        ],
                        "offerings": [
                            {
                                "price": product.price if to_int(product.price) < 50000 else 500,
                                "quantity": product.qty if product.qty > 0 or product.qty < 1000 else 999,
                                "is_enabled": True if not variant.invisible else False
                            }
                        ]
                    }
                    inventory_variants.append(variant_request_data)
                elif len(list_variant_attribute) <= 1:
                    variant_request_data = {
                        "sku": product.sku,
                        "property_values": [
                            {
                                "property_id": 513,
                                "value_ids": [
                                ],
                                "property_name": list_variant_attribute[0],
                                "values": [
                                    list_variant_attribute[0],
                                ]
                            },
                        ],
                        "offerings": [
                            {
                                "price": product.price if to_int(product.price) < 50000 else 500,
                                "quantity": product.qty if product.qty > 0 or product.qty < 1000 else 999,
                                "is_enabled": True if not variant.invisible else False
                            }
                        ]
                    }
                    inventory_variants.append(variant_request_data)
                else:
                    continue
                payload = {
                    'products': inventory_variants
                }
                path = f"/application/listings/{product_id}/inventory"
                self.api(method="PUT", extpath=path, data=payload)
        self._extend_product_map = copy.deepcopy(eemap)
        return Response().success()
