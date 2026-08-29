import openpyxl  
wb = openpyxl.load_workbook('bench/data/gaia/attachments/3da89939-209c-4086-8520-7eb734e6b4ef.xlsx', data_only=True)  
ws = wb.active  
for r in ws.iter_rows(values_only=True):  
    print(r)  
