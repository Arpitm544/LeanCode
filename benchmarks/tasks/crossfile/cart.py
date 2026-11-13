from catalog import get_item

def discounted(key):
    item = get_item(key)
    item['price'] *= 0.5
    return item
