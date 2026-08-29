import os, openpyxl  
for f in os.listdir('bench/data/gaia/attachments'):  
    if f.endswith('.xlsx'):  
        wb = openpyxl.load_workbook(os.path.join('bench/data/gaia/attachments', f), data_only=True)  
        print(f, wb.sheetnames)  
