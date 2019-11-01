# List number of tickets opened by person

resp = FB.search(q='project:brandindex', cols='ixPersonOpenedBy')
all_cases = resp.cases.findAll('case')
counter = Counter()
for c in all_cases:
    counter[c.ixPersonOpenedBy.get_text()] += 1

for n, count in counter.most_common(10):
    p = FB.viewPerson(ixPerson=int(n))
    print(f'{p.person.sFullName.text},{count}')
