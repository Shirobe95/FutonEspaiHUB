import os
import tkinter as tk
from tkinter import ttk, messagebox


# Para cargar el excel con los datos
import openpyxl

# Try a few likely locations for the data file (relative to this file)
data = []
_this_dir = os.path.dirname(__file__)
candidates = [
    os.path.join(_this_dir, '..', 'Futon Spai', 'data.xlsx'),
    os.path.join(_this_dir, '..', 'data.xlsx'),
    os.path.join(_this_dir, 'data.xlsx'),
    os.path.join(os.getcwd(), 'Futon Spai', 'data.xlsx'),
    os.path.join(os.getcwd(), 'data.xlsx'),
    'Futon Spai/data.xlsx',
    'data.xlsx',
]

wb = None
for path in candidates:
    try:
        if os.path.exists(path):
            wb = openpyxl.load_workbook(path, data_only=True)
            print(f"Loaded data file: {path}")
            break
    except Exception:
        pass

if wb is None:
    print("Warning: data.xlsx not found in expected locations. 'data' will be empty.")
else:
    sheet = wb.active
    # Read rows (skip header row) and store as: [index, col1, col2, ...]
    for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=1):
        item = [i]
        item.extend(list(row))
        data.append(item)

if data:
    print(data[0])


# Caracteristicas que seran variables de la clase de cada objeto
RotacionC = None
No_bulto = None
Unidad = None
Peso = None
M_3 = None
Precio = None

# Variables con valores
Importe_Descarga = 250
PC_Gastos_Manipulacio = 7
PC_Gastos_Financiacion = 7
Importes_Varios = 100
PC_Varios = 0.86
Coste_Total_Descarga_Futones_IVA = 302.5
Coste_Descarga_Futones_Mas_IVA = 1.69
IVA_Recargo_Equivalencia = 26.60/100
Coste_Diario_Almacenaje_xM3 = 0.374
Coste_Descarga_Futones = 1.69
PC_Plus = 0


# Variables entrada Madera y Tatamis
Precio_Dolares_MT = None
Precio_Euros_MT = None
Importe_MT = None
Total_Articulos_MT = None
Factura_Transporte_Importacion = None
Derechos_Aranceles = None


# Variables a calcular Madera y Futones
Tasa_de_Cambio = None  # Precio Euros / Precio Dolares
Importe_Transporte = None  # Factura_Transporte_Importacion + Derechos_Aranceles
Coste_Total_MT = None  # Precio_Euros_MT + Importe_Transporte
PC_Coste_Transporte = None  # Importe / Coste Total
PC_Descarga = None   # Importe Descarga / Coste Total

PC_Suma = None    # PC_Coste_Trasnporte + PC_Descarga + PC_Gastos + PC_Varios

Coste_Euros_x_Articulos = None  # Precio_Euros / Total_Articulos

Importe_Gastos_Aplicables = None  # PC_Suma x Coste_Euros_x_Articulos

# Coste_Euros_x_Articulo + Importe_Gastos_Aplicables
Total_Coste_Descarga_sin_Almacenaje = None


# Variables a calcular para Precio Total de ambos
# M_3 x RotacionC x Coste_Diario_Almacenaje_xM3
Coste_Diario_Almacenaje_xM3 = None
IVA_Coste_Diario_Almacenaje_xM3 = None  # Coste_Diario_Almacenaje_xM3 x 1.21
Coste_Unitario_Picking = None  # (No_buto x 0.3) + 4.12
IVA_Coste_Unitario_Picking = None  # Coste_Unitario_Picking x 1.21

Precio_Total = None  # Total_Coste_Descarga + Coste_Diario_Almacenaje_xM3 + IVA_Coste_Diario_Almacenaje_xM3 + Coste_Unitario_Picking


def Calculo_Maderas_Tatamis_Coste_Trasnportacion(Precio_Dolares_MT, Precio_Euros_MT, Factura_Transporte_Importacion, Derechos_Aranceles,Precio,Codigo_Item):

    global Tasa_de_Cambio
    if Precio_Euros_MT == 0:
        print("Error: Precio_Euros_MT es 0, no se puede calcular la tasa de cambio")
        return None
    Tasa_de_Cambio = round(Precio_Dolares_MT / Precio_Euros_MT, 3)

    print("Tasa de Cambio: ", Tasa_de_Cambio)
    print("-----------------------------------------")

    Importe_Transporte = Factura_Transporte_Importacion + Derechos_Aranceles
    print("Importe Transporte: ", Importe_Transporte)
    print("-----------------------------------------")

    PC_Coste_Transporte = round(
        (Importe_Transporte / Precio_Euros_MT) * 100, 2)

    print("Por ciento Gastos de Trasnporte:", PC_Coste_Transporte)
    print("-----------------------------------------")

    PC_Descarga = round((Importe_Descarga*100)/Precio_Euros_MT, 2)

    print("Por ciento Descarga:", PC_Descarga)
    print("-----------------------------------------")

    PC_Varios = round((Importes_Varios / Precio_Euros_MT)*100, 2)

    PC_Suma = round(PC_Coste_Transporte + PC_Descarga +
                    PC_Gastos_Financiacion + PC_Gastos_Manipulacio + PC_Varios, 2)
    print("Suma de por cientos:", PC_Suma)
    print("-----------------------------------------")

    Total_Precio_Coste = round(Precio / Tasa_de_Cambio, 2)
    print("Total Precio Coste por Articulo: ", Total_Precio_Coste)
    print("-----------------------------------------")

    Importe_Gastos_Aplicables = round(Total_Precio_Coste * PC_Suma/100, 2)
    print("Importe de Gastos Aplicables: ", Importe_Gastos_Aplicables)
    print("-----------------------------------------")

    Total_Coste_Descarga_sin_Almacenaje = round(
        Total_Precio_Coste + Importe_Gastos_Aplicables, 2)
    print("Total Coste Articulo Descargado sin Almacenaje: ",
          Total_Coste_Descarga_sin_Almacenaje)
    print("-----------------------------------------")

    #Ya aqui necesito los parametros del item

    item_found = None
    for item in data:
        # Compare Codigo_Item with first data column (item[1])
        try:
            if item[1] == Codigo_Item:
                item_found = item
                break
        except Exception:
            continue

    if item_found is None:
        print("Articulo no encontrado")
        return None

    # Safely extract fields with defaults
    try:
        M_3 = float(item_found[3])
    except Exception:
        M_3 = 0.0
    try:
        RotacionC = float(item_found[4])
    except Exception:
        RotacionC = 0.0
    try:
        No_bulto = int(item_found[5])
    except Exception:
        No_bulto = 1

    Coste_Almacenaje_Mas_IVA = round(0.374 * M_3 * RotacionC * 1.21, 4)

    print("Coste Almacenaje + IVA : ", Coste_Almacenaje_Mas_IVA)
    print("-----------------------------------------")

    Coste_Unitario_Picking_Mas_IVA = round(((No_bulto*0.3)+4.12)*1.21, 3)

    print("Coste Unitario del Picking + IVA: ", Coste_Unitario_Picking_Mas_IVA)
    print("-----------------------------------------")

    Precio_Coste_Final = round(
        Coste_Almacenaje_Mas_IVA + Coste_Unitario_Picking_Mas_IVA + Total_Coste_Descarga_sin_Almacenaje, 2)

    print("Precio Coste Final: ", Precio_Coste_Final)
    print("-----------------------------------------")

    item_calculado = [Tasa_de_Cambio,Importe_Transporte,PC_Coste_Transporte,PC_Descarga,PC_Suma,Total_Precio_Coste,Importe_Gastos_Aplicables,Total_Coste_Descarga_sin_Almacenaje,item_found,Coste_Almacenaje_Mas_IVA,Coste_Unitario_Picking_Mas_IVA,Precio_Coste_Final]

    return item_calculado


# Por articulos

"""def Calculo_Total_Coste_Sin_Almacenaje(Precio):

    Total_Precio_Coste = round(Precio / Tasa_de_Cambio, 2)
    print("Total Precio Coste por Articulo: ", Total_Precio_Coste)
    print("-----------------------------------------")

    Importe_Gastos_Aplicables = round(Total_Precio_Coste * PC_Suma/100, 2)
    print("Importe de Gastos Aplicables: ", Importe_Gastos_Aplicables)
    print("-----------------------------------------")

    global Total_Coste_Descarga_sin_Almacenaje
    Total_Coste_Descarga_sin_Almacenaje = round(
        Total_Precio_Coste + Importe_Gastos_Aplicables, 2)
    print("Total Coste Articulo Descargado sin Almacenaje: ",
          Total_Coste_Descarga_sin_Almacenaje)
    print("-----------------------------------------")"""


# Futones
# Variables de entrada Futones
Coste_Importe_Transporte_IVA_F = None
M_3_Total_Camion_F = None
M_3_Total_Unidades = None
Cantidad_Unidades = None
Cantidad_Futones = None  # No se cuentan las fundas
Precio_Compra = None  # En Euros


# Variables a calcular Futones
Coste_Transporte_F_Mas_IVA = None
Coste_Transporte_F_X_M_3 = None
Coste_Transporte_F_X_M_3_X_Producto = None
Coste_Transporte_F_Total_Referencia = None
Precio_Compra_IVA_RE_Incluido = None


def Calculo_Coste_Final_Con_Descarga_Futones(Coste_Transporte_F_Mas_IVA, M_3_Total_Camion_F, Unidad, Cantidad_Productos, Precio_Ekomat,Codigo_Item):
    item_found = None
    for item in data:
        try:
            if item[1] == Codigo_Item:
                item_found = item
                break
        except Exception:
            continue

    if item_found is None:
        print("Articulo no encontrado")
        return

    try:
        M_3 = float(item_found[3])
    except Exception:
        M_3 = 0.0
    try:
        RotacionC = float(item_found[4])
    except Exception:
        RotacionC = 0.0
    try:
        No_bulto = int(item_found[5])
    except Exception:
        No_bulto = 1

    if M_3_Total_Camion_F == 0:
        print("Error: M_3_Total_Camion_F es 0, no se puede dividir")
        return None
    Coste_Transporte_F_X_M_3 = round(
        Coste_Transporte_F_Mas_IVA/M_3_Total_Camion_F, 2)
    print("Coste Transporte por M3: ", Coste_Transporte_F_X_M_3)
    print("-----------------------------------------")

    Coste_Transporte_F_X_M_3_X_Producto = round(
        Coste_Transporte_F_X_M_3 * M_3, 2)
    print("Coste Transporte por M3 por Producto: ",
          Coste_Transporte_F_X_M_3_X_Producto)
    print("-----------------------------------------")

    Coste_Transporte_F_Total_Referencia = round(
        Unidad * Coste_Transporte_F_X_M_3_X_Producto, 2)
    print("Coste Transporte Total Comprados por Referencia: ",
          Coste_Transporte_F_Total_Referencia)
    print("-----------------------------------------")

    Coste_Descarga_Por_Producto_Mas_IVA = round(
        Coste_Total_Descarga_Futones_IVA / Cantidad_Productos, 2)
    print("Coste de descarga por producto + IVA: ",
          Coste_Descarga_Por_Producto_Mas_IVA)
    print("-----------------------------------------")

    Coste_Descarga_Total_Productos_Comprados_X_Referencia = round(
        Unidad * Coste_Descarga_Por_Producto_Mas_IVA, 3)
    print("Coste Descarga Total de Productos Comprados por Referencia: ",
          Coste_Descarga_Total_Productos_Comprados_X_Referencia)
    print("-----------------------------------------")

    Importe_IVA_RecargoEquivalencia = round(Precio_Ekomat * 0.262, 2)
    print("Importe de IVA + RE: ", Importe_IVA_RecargoEquivalencia)
    print("-----------------------------------------")

    Precio_Compra_IVA_RE_Incluido = Precio_Ekomat + Importe_IVA_RecargoEquivalencia
    print("Precio Compra con IVA y RE incluidos: ",
          Precio_Compra_IVA_RE_Incluido)
    print("-----------------------------------------")

    Coste_Transporte_F_X_M_3_X_Producto = round(
        Coste_Transporte_F_X_M_3 * M_3, 2)
    print("Coste Transporte por M3 por Producto 2: ",
          Coste_Transporte_F_X_M_3_X_Producto)

    Coste_Final_Con_Descarga_Futones = Coste_Transporte_F_X_M_3_X_Producto + \
        Coste_Descarga_Futones + Precio_Compra_IVA_RE_Incluido
    print("Coste Final Con Descarga de Futones: ",
          Coste_Final_Con_Descarga_Futones)

    Coste_Almacenaje_Mas_IVA = round(0.374 * M_3 * RotacionC * 1.21, 4)

    print("Coste Almacenaje + IVA : ", Coste_Almacenaje_Mas_IVA)
    print("-----------------------------------------")

    Coste_Unitario_Picking_Mas_IVA = round(((No_bulto*0.3)+4.12)*1.21, 3)

    print("Coste Unitario del Picking + IVA: ", Coste_Unitario_Picking_Mas_IVA)
    print("-----------------------------------------")

    Precio_Coste_Final = round(
        Coste_Almacenaje_Mas_IVA + Coste_Unitario_Picking_Mas_IVA + Coste_Final_Con_Descarga_Futones, 2)

    print("Precio Coste Final: ", Precio_Coste_Final)
    print("-----------------------------------------")

    # Return a list of calculated values so the caller can display them
    item_calculado_f = [
        Coste_Transporte_F_X_M_3,
        Coste_Transporte_F_X_M_3_X_Producto,
        Coste_Transporte_F_Total_Referencia,
        Coste_Descarga_Por_Producto_Mas_IVA,
        Coste_Descarga_Total_Productos_Comprados_X_Referencia,
        Importe_IVA_RecargoEquivalencia,
        Precio_Compra_IVA_RE_Incluido,
        Coste_Final_Con_Descarga_Futones,
        Coste_Almacenaje_Mas_IVA,
        Coste_Unitario_Picking_Mas_IVA,
        Precio_Coste_Final,
        item_found,
    ]

    return item_calculado_f
    

# Calculo_Coste_Final_Con_Descarga_Futones(3980.90,72.97,0.504,4,30.43)


# Precio Coste Final

def Calculo_Coste_Final(Coste_Diario_Almacenaje_xM3, M_3, RotacionC, No_bulto, Coste_Descarga):

    # Coste_Diario_Almacenaje_xM3 = 0.374
    # M_3 = 0.1074
    # RotacionC = 0.42192
    # No_bulto = 1

    Coste_Almacenaje_Mas_IVA = round(0.374 * M_3 * RotacionC * 1.21, 4)

    print("Coste Almacenaje + IVA : ", Coste_Almacenaje_Mas_IVA)
    print("-----------------------------------------")

    Coste_Unitario_Picking_Mas_IVA = round(((No_bulto*0.3)+4.12)*1.21, 3)

    print("Coste Unitario del Picking + IVA: ", Coste_Unitario_Picking_Mas_IVA)
    print("-----------------------------------------")

    Precio_Coste_Final = round(
        Coste_Almacenaje_Mas_IVA + Coste_Unitario_Picking_Mas_IVA + Coste_Descarga, 2)

    print("Precio Coste Final: ", Precio_Coste_Final)
    print("-----------------------------------------")


print("-----------------------------------------")
print("-----------------------------------------")
print("-----------------------------------------")



# Definicion de la ventana
ventana_principal = tk.Tk()
ventana_principal.title("Calculo de Precio FutonSpai")
ventana_principal.geometry("800x600")

"""
label_txt = tk.Label(ventana_principal,text="Seleccion de opcion",font=("Arial",14))
label_txt.pack(pady=10)


botton = tk.Button(ventana_principal,text="Calcular",command=NULL)
botton.pack()
"""
# Dividir las areas de la ventana
frame_izquierdo = tk.Frame(ventana_principal, padx=10, pady=10,width=250, bg="lightblue")
frame_izquierdo.pack(side="left", fill="y",padx=5,pady=5 )

# Right side: make a scrollable area so added items can be scrolled through
right_container = tk.Frame(ventana_principal)
right_container.pack(side="right", fill="both", expand=True)

canvas = tk.Canvas(right_container, bg="lightgrey")
v_scroll = tk.Scrollbar(right_container, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=v_scroll.set)
v_scroll.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)


# Inner frame where items will be added. Keep its width in sync with the canvas
frame_derecho = tk.Frame(canvas, padx=0, pady=0, bg="lightgrey")
window_id = canvas.create_window((0, 0), window=frame_derecho, anchor='nw')

def _on_frame_configure(event):
    # Update scrollregion to include new widgets
    canvas.configure(scrollregion=canvas.bbox("all"))

frame_derecho.bind("<Configure>", _on_frame_configure)

def _on_canvas_configure(event):
    # Make inner frame the same width as the canvas so child widgets can fill to the scrollbar
    try:
        canvas.itemconfig(window_id, width=event.width)
    except Exception:
        pass

canvas.bind('<Configure>', _on_canvas_configure)

def _on_mousewheel(event):
    # For Windows, event.delta is multiple of 120
    canvas.yview_scroll(int(-1*(event.delta/120)), "units")

canvas.bind_all("<MouseWheel>", _on_mousewheel)

# Definir cada seccion
opciones_calculo = ["Maderas y Tatamis", "Futones"]
selector_calculo = ttk.Combobox(
    frame_izquierdo, values=opciones_calculo, state="readonly")
selector_calculo.current(0)
selector_calculo.pack(fill="x",  pady=10)


def on_selector_change(event=None):
    mode = selector_calculo.get()
    # default common field: Codigo stays visible
    if mode == "Maderas y Tatamis":
        # show maderas fields
        lbl_precio_dolares.pack(fill="x", pady=(5,0))
        entry_precio_dolares.pack(fill="x",pady=(0,10))
        lbl_precio_euros.pack(fill="x", pady=(5,0))
        entry_precio_euros.pack(fill="x",pady=(0,10))
        lbl_factura_transporte.pack(fill="x", pady=(5,0))
        entry_factura_transporte.pack(fill="x",pady=(0,10))
        lbl_derechos_aranceles.pack(fill="x", pady=(5,0))
        entry_derechos_aranceles.pack(fill="x",pady=(0,10))
        lbl_precio_item.pack(fill="x", pady=(5,0))
        entry_precio_item.pack(fill="x",pady=(0,10))

        # hide futones fields
        lbl_coste_transporte_f.pack_forget()
        entry_coste_transporte_f.pack_forget()
        lbl_m3_total_camion_f.pack_forget()
        entry_m3_total_camion_f.pack_forget()
        lbl_unidad.pack_forget()
        entry_unidad.pack_forget()
        lbl_cantidad_productos.pack_forget()
        entry_cantidad_productos.pack_forget()
        lbl_precio_ekomat.pack_forget()
        entry_precio_ekomat.pack_forget()

    else:
        # show futones fields
        lbl_precio_dolares.pack_forget()
        entry_precio_dolares.pack_forget()
        lbl_precio_euros.pack_forget()
        entry_precio_euros.pack_forget()
        lbl_factura_transporte.pack_forget()
        entry_factura_transporte.pack_forget()
        lbl_derechos_aranceles.pack_forget()
        entry_derechos_aranceles.pack_forget()
        lbl_precio_item.pack_forget()
        entry_precio_item.pack_forget()

        lbl_coste_transporte_f.pack(fill="x", pady=(5,0))
        entry_coste_transporte_f.pack(fill="x",pady=(0,10))
        lbl_m3_total_camion_f.pack(fill="x", pady=(5,0))
        entry_m3_total_camion_f.pack(fill="x",pady=(0,10))
        lbl_unidad.pack(fill="x", pady=(5,0))
        entry_unidad.pack(fill="x",pady=(0,10))
        lbl_cantidad_productos.pack(fill="x", pady=(5,0))
        entry_cantidad_productos.pack(fill="x",pady=(0,10))
        lbl_precio_ekomat.pack(fill="x", pady=(5,0))
        entry_precio_ekomat.pack(fill="x",pady=(0,10))

selector_calculo.bind('<<ComboboxSelected>>', on_selector_change)

lbl_codigo = tk.Label(frame_izquierdo,text="Codigo del articulo")
lbl_codigo.pack(fill="x", pady=(5,0))
entry_codigo = tk.Entry(frame_izquierdo)
entry_codigo.pack(fill="x",pady=(0,10))

lbl_precio_dolares = tk.Label(frame_izquierdo,text="Precio en Dolares")
lbl_precio_dolares.pack(fill="x", pady=(5,0))
entry_precio_dolares = tk.Entry(frame_izquierdo)
entry_precio_dolares.pack(fill="x",pady=(0,10))

lbl_precio_euros = tk.Label(frame_izquierdo,text="Precio en Euros")
lbl_precio_euros.pack(fill="x", pady=(5,0))
entry_precio_euros = tk.Entry(frame_izquierdo)
entry_precio_euros.pack(fill="x",pady=(0,10))

lbl_factura_transporte = tk.Label(frame_izquierdo,text="Factura de Trasnporte")
lbl_factura_transporte.pack(fill="x", pady=(5,0))
entry_factura_transporte = tk.Entry(frame_izquierdo)
entry_factura_transporte.pack(fill="x",pady=(0,10))

lbl_derechos_aranceles = tk.Label(frame_izquierdo,text="Derechos Aranceles")
lbl_derechos_aranceles.pack(fill="x", pady=(5,0))
entry_derechos_aranceles = tk.Entry(frame_izquierdo)
entry_derechos_aranceles.pack(fill="x",pady=(0,10))

lbl_precio_item = tk.Label(frame_izquierdo,text="Precio del Articulo")
lbl_precio_item.pack(fill="x", pady=(5,0))
entry_precio_item = tk.Entry(frame_izquierdo)
entry_precio_item.pack(fill="x",pady=(0,10))

# Futones input fields (initially hidden)
lbl_coste_transporte_f = tk.Label(frame_izquierdo, text="Coste Transporte Futones (mas IVA)")
entry_coste_transporte_f = tk.Entry(frame_izquierdo)

lbl_m3_total_camion_f = tk.Label(frame_izquierdo, text="M3 Total Camion")
entry_m3_total_camion_f = tk.Entry(frame_izquierdo)

lbl_unidad = tk.Label(frame_izquierdo, text="Unidades por Referencia")
entry_unidad = tk.Entry(frame_izquierdo)

lbl_cantidad_productos = tk.Label(frame_izquierdo, text="Cantidad de Productos")
entry_cantidad_productos = tk.Entry(frame_izquierdo)

lbl_precio_ekomat = tk.Label(frame_izquierdo, text="Precio Ekomat")
entry_precio_ekomat = tk.Entry(frame_izquierdo)


def Btn_Calcular_Pressed():
    mode = selector_calculo.get()
    if mode == "Maderas y Tatamis":
        try:
            Codigo = int(entry_codigo.get())
            Precio_Dolares_MT = float(entry_precio_dolares.get())
            Precio_Euros_MT = float(entry_precio_euros.get())
            Factura_Transporte_Importacion = float(entry_factura_transporte.get())
            Derechos_Aranceles = float(entry_derechos_aranceles.get())
            Precio = float(entry_precio_item.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "Por favor introduce valores numéricos válidos en los campos.")
            return

        item_calculado = Calculo_Maderas_Tatamis_Coste_Trasnportacion(Precio_Dolares_MT,Precio_Euros_MT,Factura_Transporte_Importacion,Derechos_Aranceles,Precio,Codigo)
        if item_calculado is None:
            messagebox.showinfo("Resultado", "No se pudo calcular. Revisa entradas y datos del artículo.")
            return

        item_found = item_calculado[8]
        display_name = str(item_found[2]) if len(item_found) > 2 and item_found[2] is not None else f"Articulo {Codigo}"

        new_item_show = tk.LabelFrame(frame_derecho,text=display_name,padx=10,pady=10,bg="#e6f2ff",fg="darkblue",font=("Arial",10,"bold"))
        new_item_show.pack(fill="x",pady=5,padx=0)
        new_item_show.columnconfigure(0, weight=1)

        # Labels fill full width and use the same background as the frame to avoid white gaps
        lbl_result_tasa_cambio = tk.Label(new_item_show,text=f"Tasa de Cambio: {item_calculado[0]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_tasa_cambio.pack(fill="x")

        lbl_result_importe = tk.Label(new_item_show,text=f"Importe de Transporte: {item_calculado[1]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_importe.pack(fill="x")

        lbl_result_pc_coste_transporte = tk.Label(new_item_show,text=f"% Coste Transporte: {item_calculado[2]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_pc_coste_transporte.pack(fill="x")

        lbl_result_pc_descarga = tk.Label(new_item_show,text=f"% Coste Descarga: {item_calculado[3]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_pc_descarga.pack(fill="x")

        lbl_result_pc_suma = tk.Label(new_item_show,text=f"% Coste Suma: {item_calculado[4]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_pc_suma.pack(fill="x")

        lbl_result_pc_total_precio_coste = tk.Label(new_item_show,text=f"Total Precio Coste: {item_calculado[5]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_pc_total_precio_coste.pack(fill="x")

        lbl_result_importe_gastos_aplicables = tk.Label(new_item_show,text=f"Total Gastos Aplicables: {item_calculado[6]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_importe_gastos_aplicables.pack(fill="x")

        lbl_result_total_coste_descarga= tk.Label(new_item_show,text=f"Total Coste Descarga: {item_calculado[7]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_total_coste_descarga.pack(fill="x")

        lbl_result_coste_almacenaje_mas_iva= tk.Label(new_item_show,text=f"Coste Almacenaje + IVA: {item_calculado[9]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_coste_almacenaje_mas_iva.pack(fill="x")

        lbl_result_unitario_picking= tk.Label(new_item_show,text=f"Coste Unitario del Picking + IVA: {item_calculado[10]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_unitario_picking.pack(fill="x")

        lbl_result_precio_coste_final= tk.Label(new_item_show,text=f"Precio del Coste Final: {item_calculado[11]}",bg="#e6f2ff",anchor='w',justify="left")
        lbl_result_precio_coste_final.pack(fill="x")

    else:
        # Futones mode
        try:
            Codigo = int(entry_codigo.get())
            Coste_Transporte_F_Mas_IVA = float(entry_coste_transporte_f.get())
            M_3_Total_Camion_F = float(entry_m3_total_camion_f.get())
            Unidad = int(entry_unidad.get())
            Cantidad_Productos = int(entry_cantidad_productos.get())
            Precio_Ekomat = float(entry_precio_ekomat.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "Por favor introduce valores numéricos válidos para Futones.")
            return

        item_calculado_f = Calculo_Coste_Final_Con_Descarga_Futones(Coste_Transporte_F_Mas_IVA, M_3_Total_Camion_F, Unidad, Cantidad_Productos, Precio_Ekomat,Codigo)
        if item_calculado_f is None:
            messagebox.showinfo("Resultado", "No se pudo calcular Futones. Revisa entradas y datos del artículo.")
            return

        # item_calculado_f layout:
        # [Coste_Transporte_F_X_M_3, Coste_Transporte_F_X_M_3_X_Producto, Coste_Transporte_F_Total_Referencia,
        #  Coste_Descarga_Por_Producto_Mas_IVA, Coste_Descarga_Total_Productos_Comprados_X_Referencia,
        #  Importe_IVA_RecargoEquivalencia, Precio_Compra_IVA_RE_Incluido, Coste_Final_Con_Descarga_Futones,
        #  Coste_Almacenaje_Mas_IVA, Coste_Unitario_Picking_Mas_IVA, Precio_Coste_Final, item_found]

        item_found = item_calculado_f[11]
        display_name = str(item_found[2]) if len(item_found) > 2 and item_found[2] is not None else f"Futon {Codigo}"

        new_item_show = tk.LabelFrame(frame_derecho,text=display_name,padx=10,pady=10,bg="#eaffea",fg="darkgreen",font=("Arial",10,"bold"))
        new_item_show.pack(fill="x",pady=5,padx=0)
        new_item_show.columnconfigure(0, weight=1)

        lbl_ct_m3 = tk.Label(new_item_show, text=f"Coste Transporte por M3: {item_calculado_f[0]}", bg="#eaffea",anchor='w',justify='left')
        lbl_ct_m3.pack(fill="x")
        lbl_ct_m3_prod = tk.Label(new_item_show, text=f"Coste Transporte por Producto (M3): {item_calculado_f[1]}", bg="#eaffea",anchor='w',justify='left')
        lbl_ct_m3_prod.pack(fill="x")
        lbl_ct_total_ref = tk.Label(new_item_show, text=f"Coste Transporte Total Referencia: {item_calculado_f[2]}", bg="#eaffea",anchor='w',justify='left')
        lbl_ct_total_ref.pack(fill="x")

        lbl_coste_descarga_por_prod = tk.Label(new_item_show, text=f"Coste Descarga por Producto + IVA: {item_calculado_f[3]}", bg="#eaffea",anchor='w',justify='left')
        lbl_coste_descarga_por_prod.pack(fill="x")
        lbl_coste_descarga_total_ref = tk.Label(new_item_show, text=f"Coste Descarga Total Referencia: {item_calculado_f[4]}", bg="#eaffea",anchor='w',justify='left')
        lbl_coste_descarga_total_ref.pack(fill="x")

        lbl_iva_re = tk.Label(new_item_show, text=f"Importe IVA + RE: {item_calculado_f[5]}", bg="#eaffea",anchor='w',justify='left')
        lbl_iva_re.pack(fill="x")
        lbl_precio_compra_iva = tk.Label(new_item_show, text=f"Precio Compra (IVA+RE): {item_calculado_f[6]}", bg="#eaffea",anchor='w',justify='left')
        lbl_precio_compra_iva.pack(fill="x")

        lbl_coste_final_descarga = tk.Label(new_item_show, text=f"Coste Final con Descarga: {item_calculado_f[7]}", bg="#eaffea",anchor='w',justify='left')
        lbl_coste_final_descarga.pack(fill="x")

        lbl_coste_almacenaje = tk.Label(new_item_show, text=f"Coste Almacenaje + IVA: {item_calculado_f[8]}", bg="#eaffea",anchor='w',justify='left')
        lbl_coste_almacenaje.pack(fill="x")
        lbl_unitario_picking = tk.Label(new_item_show, text=f"Coste Unitario Picking + IVA: {item_calculado_f[9]}", bg="#eaffea",anchor='w',justify='left')
        lbl_unitario_picking.pack(fill="x")

        lbl_precio_coste_final = tk.Label(new_item_show, text=f"Precio Coste Final: {item_calculado_f[10]}", bg="#eaffea",anchor='w',justify='left')
        lbl_precio_coste_final.pack(fill="x")




# Place the calculate button pinned to the bottom of the left frame
boton_container = tk.Frame(frame_izquierdo, bg="lightblue")
boton_container.pack(side="bottom", fill="x", pady=10)

boton_calcular = tk.Button(boton_container, text="Calcular", command=Btn_Calcular_Pressed, bg="#4CAF50", fg="white", font=("Arial",10,"bold"))
boton_calcular.pack(fill="x", padx=20)

ventana_principal.mainloop()


"""
seleccion = int(input("1-Madera y Tatamis 2-Futones:"))
if (seleccion == 1):
    print("Ahora a calcular a Madera y Tatamis")
    Precio_Dolares_MT = float(input("Precio Total en Dolares:"))
    Precio_Euros_MT = float(input("Precio Total en Euros:"))
    Factura_Transporte_Importacion = float(
        input("Factura Trasnporte Importacion:"))
    Derechos_Aranceles = float(input("Derechos Aranceles:"))
    Precio = float(input("Precio:"))
    Codigo = int(input("Codigo del articulo:"))

    print("-----------------------------------------")

    Calculo_Maderas_Tatamis_Coste_Trasnportacion(
        Precio_Dolares_MT, Precio_Euros_MT, Factura_Transporte_Importacion, Derechos_Aranceles,Precio,Codigo)

    
    print("-----------------------------------------")
    Precio = float(input("Precio:"))
    print("-----------------------------------------")
    Calculo_Total_Coste_Sin_Almacenaje(Precio)
    print("-----------------------------------------")
    Coste_Diario_Almacenaje_xM3 = float(input("Coste Diario Almacenaje x M3:"))
    M_3 = float(input("M3:"))
    RotacionC = float(input("RotacionC:"))
    No_bulto = int(input("No Bultos:"))
    print("-----------------------------------------")
    Calculo_Coste_Final(Coste_Diario_Almacenaje_xM3, M_3,
                        RotacionC, No_bulto, Total_Coste_Descarga_sin_Almacenaje)
    print("-----------------------------------------")
    print("-----------------------------------------")



elif (seleccion == 2):
    print("Ahora a calcular Futones")
    Coste_Descarga_Futones_Mas_IVA = float(
        input("Coste Transporte Futones mas IVA:"))
    M_3_Total_Camion_F = float(input("M3 Total del Camion:"))
    Unidad = int(input("Unidades:"))
    Cantidad_Productos = int(input("Cantidad de productos:"))
    Precio_Ekomat = float(input("Precio Ekomat:"))
    Codigo_Item = int(input("Codigo de Articulo:"))
    print("-----------------------------------------")

    Calculo_Coste_Final_Con_Descarga_Futones(
        Coste_Descarga_Futones_Mas_IVA, M_3_Total_Camion_F, Unidad, Cantidad_Productos, Precio_Ekomat,Codigo_Item)

 
    print("-----------------------------------------")
    RotacionC = float(input("RotacionC:"))
    No_bulto = int(input("No Bultos:"))
    print("-----------------------------------------")
    Calculo_Coste_Final(Coste_Diario_Almacenaje_xM3, M_3,
                        RotacionC, No_bulto, Coste_Final_Con_Descarga_Futones)
    print("-----------------------------------------")
    print("-----------------------------------------")
    """


