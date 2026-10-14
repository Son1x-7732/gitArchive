import math

data = [
    {"ID": 1, "Outlook": "Sunny", "Temperature": "Hot", "Humidity": "High", "Wind": "Weak", "Play": "No"},
    {"ID": 2, "Outlook": "Sunny", "Temperature": "Hot", "Humidity": "High", "Wind": "Strong", "Play": "No"},
    {"ID": 3, "Outlook": "Overcast", "Temperature": "Hot", "Humidity": "High", "Wind": "Weak", "Play": "Yes"},
    {"ID": 4, "Outlook": "Rain", "Temperature": "Mild", "Humidity": "High", "Wind": "Weak", "Play": "Yes"},
    {"ID": 5, "Outlook": "Rain", "Temperature": "Cool", "Humidity": "Normal", "Wind": "Weak", "Play": "Yes"},
    {"ID": 6, "Outlook": "Rain", "Temperature": "Cool", "Humidity": "Normal", "Wind": "Strong", "Play": "No"},
    {"ID": 7, "Outlook": "Overcast", "Temperature": "Cool", "Humidity": "Normal", "Wind": "Strong", "Play": "Yes"},
    {"ID": 8, "Outlook": "Sunny", "Temperature": "Mild", "Humidity": "High", "Wind": "Weak", "Play": "No"},
    {"ID": 9, "Outlook": "Sunny", "Temperature": "Cool", "Humidity": "Normal", "Wind": "Weak", "Play": "Yes"},
    {"ID": 10, "Outlook": "Rain", "Temperature": "Mild", "Humidity": "Normal", "Wind": "Weak", "Play": "Yes"},
    {"ID": 11, "Outlook": "Sunny", "Temperature": "Mild", "Humidity": "Normal", "Wind": "Strong", "Play": "Yes"},
    {"ID": 12, "Outlook": "Overcast", "Temperature": "Mild", "Humidity": "High", "Wind": "Strong", "Play": "Yes"},
    {"ID": 13, "Outlook": "Overcast", "Temperature": "Hot", "Humidity": "Normal", "Wind": "Weak", "Play": "Yes"},
    {"ID": 14, "Outlook": "Rain", "Temperature": "Mild", "Humidity": "High", "Wind": "Strong", "Play": "No"}
]

class tree:
    def __init__ (self, name):
        self.name = name
        self.children = {}
    def addchild(self, key, child):
        self.children[key] = child

# info_gain_attributes 

def entropy(data, key="default"):
    yes_count = 0
    for i in data:
        if i["Play"] == "Yes":
            yes_count += 1

    no_count = len(data) - yes_count

    p_yes = yes_count / len(data)
    p_no = 1 - p_yes

    if p_yes == 0 or p_no == 0:
        return (0, p_yes, p_no)
    entropy = - p_yes * math.log2(p_yes) - p_no * math.log2(p_no)
    return (entropy, p_yes, p_no)

def extract_values(data, key : string)-> dict :
    values = {}
    for col in data:
        values[col[key]] = values.get(col[key], 0) + 1
    return values


def maketree(data):
    keys = []
    for k, v in data[0].items():
        keys.append(k)

    keys.remove("ID")
    keys.remove("Play")

    total_entropy, p_yes, p_no = entropy(data)
    total_count = len(data)

    if p_yes == 1:
        return tree("yes")
    if p_no == 1:
        return tree("no")

    info_gain_of_keys = []
    for key in keys:
        attributes = extract_values(data, key)
        entropy_of_attributes = []
        for attribute, count in attributes.items():
            entropy_attribute = entropy([i for i in data if i[key] == attribute])[0]
            entropy_of_attributes.append((attribute, entropy_attribute, count))
        
        info_gain = total_entropy - sum([k / total_count * j for i, j, k in entropy_of_attributes])
        info_gain_of_keys.append((key, info_gain))
    

    selected_attribute = ""
    max_info_gain = -float("inf")

    for info_gain in info_gain_of_keys:
        if info_gain[1] > max_info_gain:
            max_info_gain = info_gain[1]
            selected_attribute = info_gain[0]
    
    attribute_of_selected_key = extract_values(data, selected_attribute)
    t = tree(selected_attribute)
    for k, c in attribute_of_selected_key.items():
        temp = maketree([i for i in data if i[selected_attribute] == k])
        t.addchild(k, temp)
    
    return t


def traveltree(node):
    if not node.children:
        return node.name
    output = {}
    for k, v in node.children.items():
        output[k] = traveltree(v)
    return output



if __name__ == "__main__":
    t = maketree(data)
    output = traveltree(t)
    print(
        {t.name: output}
    )

