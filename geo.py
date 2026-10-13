# Approximate district/city centre coordinates (±5–15 km). Order matters: specific first.
import json
G=[
("quva",40.522,72.073),("rishton",40.357,71.285),("rishtan",40.357,71.285),("uchko'prik",40.533,71.050),("qo'qon",40.528,70.942),("kokand",40.528,70.942),
("qo'shtepa",40.533,71.680),("buvayda",40.627,70.927),("oltiariq",40.392,71.475),("furqat",40.585,70.700),("o'zbekiston tumani",40.330,71.000),("toshloq",40.475,71.770),
("marg'ilon",40.471,71.725),("margilan",40.471,71.725),("farg'ona sh",40.384,71.787),("fergana",40.384,71.787),("farg'ona",40.384,71.787),
("baliqchi",40.900,71.850),("jalolquduq",40.725,72.640),("paxtaobod",40.930,72.500),("xonobod",40.800,73.000),("oltinko'l",40.800,72.140),("xo'jaobod",40.670,72.560),
("shaxrixon",40.713,72.057),("andijon tumani",40.800,72.300),("andijan",40.783,72.344),("andijon",40.783,72.344),
("zangiota",41.200,69.140),("parkent",41.295,69.680),("yangiyo'l",41.112,69.047),("yangiyul",41.112,69.047),("olmaliq",40.845,69.598),("pskent",40.897,69.350),
("qibray",41.390,69.465),("yuqorichirchiq",41.330,69.580),
("toshkent shahri",41.311,69.280),("tashkent city",41.311,69.280),("chilonzor",41.275,69.205),
("qarshi",38.860,65.790),("yakkabog",38.975,66.680),("nishon",38.660,65.660),
("guliston",40.490,68.785),("gulistan",40.490,68.785),("sardoba",40.250,68.170),
("navbahor",40.140,65.300),("navoiy",40.103,65.374),("navoi",40.103,65.374),
("uzun tumani",38.370,68.000),("sho'rchi",38.000,67.790),("termiz",37.224,67.278),
("kattaqo'rg'on",39.900,66.260),("oqdaryo",39.850,66.800),("urgut",39.400,67.240),("pastdarg'om",39.700,66.700),("samarqand tumani",39.620,67.000),("samarqand",39.654,66.959),("samarkand",39.654,66.959),
("do'stlik tumani",40.524,68.035),("zafarobod",40.400,67.750),("jizzax",40.116,67.842),
("qorako'l",39.500,63.850),("jondor",39.730,64.180),("olot",39.420,63.800),("kogon",39.722,64.551),("kagan",39.722,64.551),("buxoro tumani",39.800,64.400),
("romitan",39.930,64.380),("shofirkon",40.120,64.500),("vobkent",40.030,64.520),("buxoro",39.768,64.421),("bukhara",39.768,64.421),
("bog'ot",41.350,60.850),("gurlan",41.840,60.390),("urganch",41.550,60.633),
]
R=json.load(open('suppliers.json'))
miss=[]
for r in R:
    s=(r['adr']+' '+r['loc']).lower().replace('`',"'").replace('‘',"'").replace('’',"'")
    # registry address wins: put adr first
    s1=r['adr'].lower().replace('`',"'")
    hit=None
    for src in (s1,s):
        for k,la,lo in G:
            if k in src: hit=(la,lo,k);break
        if hit:break
    if hit: r['lat'],r['lon']=hit[0],hit[1]
    else: miss.append(r['n'])
json.dump(R,open('suppliers.json','w'),ensure_ascii=False)
print('missing',miss)
