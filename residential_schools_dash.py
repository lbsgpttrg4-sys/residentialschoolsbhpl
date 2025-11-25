import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- 1. CONFIGURATION AND DATA LOADING ---
SHEET_ID = '1d61LeVAPxdT7Ivx5pEmNJkJYb3YMLqyKbYSPOYivk-Q'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0'

# Standardize column names
COLUMN_MAPPING = {
    'Sl_no': 'sl_no', 'School_Name': 'school_name', 'Totel_enrolled_students': 'enrolled_students', 
    'Vacant_seats': 'vacant_seats', 'Driniking water Facility (Yes/No)': 'drinking_water',
    'RO Plant available or not': 'ro_plant', 'No of class rooms available': 'class_rooms_available', 
    'No of class rooms required': 'class_rooms_required', 'No of Darmitories Available': 'dormitories_available', 
    'No of Darmitories Required': 'dormitories_required', 'No of Functional Toilets Availabale': 'toilets_functional_available',
    'No of Toilets Required': 'toilets_required', 'No of Bathrooms Available': 'bathrooms_available', 
    'No of Bathrooms Required': 'bathrooms_required', 'No of Dual Desk Tables Available': 'dual_desk_available', 
    'No of Dual Desk Tables Required': 'dual_desk_required', 'No of Computers Available': 'computers_available', 
    'Internet Facility available(yes /No)': 'internet_facility', 'No of Dining Tables Availabale': 'dining_tables_available', 
    'No of Dining Tables Required': 'dining_tables_required', 'No of cots Available': 'cots_available', 
    'No of cots Required': 'cots_required', 'No of Matresses available': 'matresses_available', 
    'No of Matresses required': 'matresses_required', 'No of Blankets Available': 'blankets_available', 
    'No of Blankets Required': 'blankets_required', 'Solar Water Heater/ Geyser Available': 'swh_available', 
    'Solar Water Heater/ Geyser Requirement': 'swh_required', 'No of IFP panels availble': 'ifp_panels_available', 
    'Vacancy': 'vacancy_count', 'Remarks': 'remarks'
}

# Define departments (kept for cleaning/categorization)
def get_department(school_name):
    name = str(school_name).upper()
    if name.startswith('KGBV'): return 'KGBV (Girls)'
    elif name.startswith('TGMS'): return 'TGMS (Co-ed)'
    elif name.startswith('PMSHRI'): return 'PMSHRI (Co-ed)'
    else: return 'Other'

@st.cache_data(ttl=600)
def load_and_clean_data(url):
    """Loads, renames, and cleans the data from the Google Sheet."""
    try:
        df = pd.read_csv(url)
    except Exception as e:
        st.error(f"Error loading data from Google Sheet: {e}")
        return pd.DataFrame()

    df.rename(columns=COLUMN_MAPPING, inplace=True)
    df['school_name'] = df['school_name'].astype(str).str.strip()
    
    # Clean Yes/No columns
    yes_no_cols = ['drinking_water', 'ro_plant', 'internet_facility', 'swh_available', 'swh_required']
    for col in yes_no_cols:
        df[col] = df[col].astype(str).str.lower().str.strip().apply(
            lambda x: 'yes' if 'yes' in x else ('no' if 'no' in x else x)
        )
        
    # Clean numeric columns
    numeric_cols = list(set(COLUMN_MAPPING.values()) - set(['sl_no', 'school_name', 'drinking_water', 'ro_plant', 'internet_facility', 'remarks']))
    for col in numeric_cols:
        df[col] = df[col].astype(str).str.replace(r'[^0-9\.\-]', '', regex=True)
        df[col] = df[col].apply(lambda x: pd.to_numeric(x.split('-')[0].split('$')[0].strip(), errors='coerce'))
        df[col] = df[col].fillna(0).astype(int)

    # Add Calculated Metrics
    df['Department'] = df['school_name'].apply(get_department)
    df['enrolled_students_safe'] = df['enrolled_students'].replace(0, np.nan)
    
    # --- PER-STUDENT RATIOS (Available/Enrolled Student) ---
    df['ratio_classrooms'] = df['class_rooms_available'] / df['enrolled_students_safe'] * 100
    df['ratio_toilets'] = df['toilets_functional_available'] / df['enrolled_students_safe'] * 100
    df['ratio_bathrooms'] = df['bathrooms_available'] / df['enrolled_students_safe'] * 100
    df['ratio_desks'] = df['dual_desk_available'] / df['enrolled_students_safe']
    df['ratio_cots'] = df['cots_available'] / df['enrolled_students_safe']
    df['ratio_computers'] = df['computers_available'] / df['enrolled_students_safe']
    
    return df

# Initialize session state for interactivity
if 'selected_department' not in st.session_state:
    st.session_state['selected_department'] = 'All'

# --- 2. STREAMLIT APP LAYOUT ---

df_original = load_and_clean_data(SHEET_URL)
if df_original.empty:
    st.stop()

st.set_page_config(layout="wide", page_title="School Resource Summary Dashboard",
                   initial_sidebar_state="expanded")

st.title("🏡 School Infrastructure and Resource Dashboard")

# --- Sidebar for Global Filter ---
st.sidebar.header("Global Filters")
department_options = ['All'] + sorted(df_original['Department'].unique().tolist())
st.session_state['selected_department'] = st.sidebar.selectbox(
    "Filter by Department",
    department_options
)

# Apply department filter
if st.session_state['selected_department'] != 'All':
    df_filtered = df_original[df_original['Department'] == st.session_state['selected_department']].copy()
else:
    df_filtered = df_original.copy()

# --- Functions for Charts ---

def create_fulfillment_chart(df, col_available, col_required, title, unit='units'):
    """
    Creates a chart showing available vs required (deficiency).
    Fulfillment calculated strictly as: Available / (Available + Required).
    """
    available = df[col_available].sum()
    # 'Required' column is strictly interpreted as the ADDITIONAL DEFICIENCY (D)
    required_deficiency = df[col_required].sum() 
    
    # Total effective need = Available + Deficiency
    total_need = available + required_deficiency
    
    # Fulfillment calculation: A / (A + D)
    fulfillment_ratio = (available / total_need) if total_need > 0 else 1.0

    # Prepare data for stacked bar chart, ensuring the order is Deficient, then Available
    # This ordering ensures 'Available' is placed on the left, and 'Deficient' is on the right
    data = pd.DataFrame({
        'Status': ['Deficient', 'Available'],
        'Count': [required_deficiency, available]
    })
    data['Category'] = 'Total Need' 
    
    # Filter out rows with zero count
    data = data[data['Count'] > 0]
    
    # Define the color map: Red for Deficient, Green for Available
    COLOR_MAP = {'Available': '#2ECC71', 'Deficient': '#E74C3C'} # Red for deficiency

    fig = px.bar(
        data, 
        x='Count', 
        y='Category',
        orientation='h',
        color='Status',
        color_discrete_map=COLOR_MAP, # <-- Explicitly apply the color map
        category_orders={"Status": ["Available", "Deficient"]}, # <-- Ensure legend order
        title=f'{title} Fulfillment ({fulfillment_ratio:.1%})',
        text_auto=True 
    )
    
    max_x = total_need
    
    fig.update_layout(
        xaxis_title=f"Total {unit.title()}",
        yaxis_title="",
        height=180,
        margin=dict(t=40, b=10, l=10, r=10),
        showlegend=True,
        barmode='stack',
        xaxis_range=[0, max_x * 1.05] if max_x > 0 else [0, 1]
    )
    
    return fig

def create_yes_no_chart(df, col, title):
    """Creates a chart showing Yes/No status distribution."""
    yes_count = df[col].astype(str).str.lower().str.contains('yes').sum()
    total = df.shape[0]
    no_count = total - yes_count
    yes_percent = (yes_count / total)  if total > 0 else 0
    
    data = pd.DataFrame({
        'Status': ['Yes', 'No'],
        'Count': [yes_count, no_count]
    })
    
    fig = px.pie(
        data,
        names='Status',
        values='Count',
        color='Status',
        color_discrete_map={'Yes': '#00AEEF', 'No': '#FF6347'},
        hole=.4,
        title=f'{title} ({yes_percent:.1%} Yes)',
        hover_data=['Count']
    )
    fig.update_traces(textinfo='percent+label')
    fig.update_layout(height=300, margin=dict(t=40, b=0, l=0, r=0))
    return fig

# --- Main Dashboard Tabs ---

tab1, tab2 = st.tabs(["✅ Global Summary & Fulfillment", "📉 Per-Student Deficiency Analysis"])

with tab1:
    st.header(f"Summary & Enrollment: {st.session_state['selected_department']}")
    
    # 1. Four Key KPIs
    total_schools = df_filtered.shape[0]
    total_enrolled = df_filtered['enrolled_students'].sum()
    total_vacant = df_filtered['vacant_seats'].sum()
    total_capacity = total_enrolled + total_vacant
    overall_vacancy_percent = (total_vacant / total_capacity) * 100 if total_capacity > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric(label="Total Schools", value=total_schools)
    with col2: st.metric(label="Total Enrolled Students", value=f"{total_enrolled:,.0f}")
    with col3: st.metric(label="Total Vacant Seats", value=f"{total_vacant:,.0f}")
    with col4: st.metric(label="Overall Vacancy Rate", value=f"{overall_vacancy_percent:.1f}%")
        
    st.markdown("---")

    st.subheader("Facility Status: Yes/No Availability")
    
    # 2. Facility Percentage Charts (Yes/No)
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1: st.plotly_chart(create_yes_no_chart(df_filtered, 'drinking_water', "Drinking Water"), use_container_width=True)
    with col_f2: st.plotly_chart(create_yes_no_chart(df_filtered, 'ro_plant', "RO Plant"), use_container_width=True)
    with col_f3: st.plotly_chart(create_yes_no_chart(df_filtered, 'internet_facility', "Internet Facility"), use_container_width=True)
    
    st.markdown("---")

    # 3. Available vs. Required Charts (Horizontal Bars)
    st.subheader("Resource Stock Fulfillment (Available vs. Required)")
    
    col_r1, col_r2 = st.columns(2)
    with col_r1: st.plotly_chart(create_fulfillment_chart(df_filtered, 'class_rooms_available', 'class_rooms_required', "Classrooms", 'rooms'), use_container_width=True)
    with col_r2: st.plotly_chart(create_fulfillment_chart(df_filtered, 'dormitories_available', 'dormitories_required', "Dormitories", 'rooms'), use_container_width=True)

    col_r3, col_r4 = st.columns(2)
    with col_r3: st.plotly_chart(create_fulfillment_chart(df_filtered, 'toilets_functional_available', 'toilets_required', "Functional Toilets", 'units'), use_container_width=True)
    with col_r4: st.plotly_chart(create_fulfillment_chart(df_filtered, 'bathrooms_available', 'bathrooms_required', "Bathrooms", 'units'), use_container_width=True)

    col_r5, col_r6 = st.columns(2)
    with col_r5: st.plotly_chart(create_fulfillment_chart(df_filtered, 'dual_desk_available', 'dual_desk_required', "Dual Desks", 'tables'), use_container_width=True)
    with col_r6: st.plotly_chart(create_fulfillment_chart(df_filtered, 'cots_available', 'cots_required', "Cots", 'units'), use_container_width=True)

with tab2:
    st.header("Per-Student Deficiency Analysis: Top 5 Schools")
    st.info("The tables below highlight the **Top 5 schools** with the **lowest resource ratio** (highest deficiency) per enrolled student for each category.")
    
    # Select available ratio columns and drop schools with 0 enrollment
    ratio_cols = [c for c in df_filtered.columns if c.startswith('ratio_')]
    ratios_df = df_filtered[['school_name', 'enrolled_students'] + ratio_cols].dropna(subset=['enrolled_students'] + ratio_cols).copy()
    
    ratio_mapping = {
        'ratio_classrooms': 'Classrooms / 100 Students',
        'ratio_toilets': 'Toilets / 100 Students',
        'ratio_bathrooms': 'Bathrooms / 100 Students',
        'ratio_desks': 'Dual Desks / Student',
        'ratio_cots': 'Cots / Student',
        'ratio_computers': 'Computers / Student'
    }

    if ratios_df.empty:
        st.warning("No schools with sufficient enrollment data to calculate per-student ratios.")
    else:
        # Create columns for table layout
        chart_cols = st.columns(2)
        
        for i, (ratio_col, display_name) in enumerate(ratio_mapping.items()):
            if ratio_col in ratios_df.columns:
                # Rank schools by lowest value (worst coverage)
                df_ranked = ratios_df.sort_values(by=ratio_col, ascending=True).head(5)
                
                # Prepare table data: School Name and Ratio Value
                df_table = df_ranked[['school_name', ratio_col]].copy()
                df_table.columns = ['School Name', display_name]
                
                # Format the ratio value for better display
                if '100 Students' in display_name:
                    df_table[display_name] = df_table[display_name].round(2).apply(lambda x: f"{x:.2f}")
                else:
                    df_table[display_name] = df_table[display_name].round(3).apply(lambda x: f"{x:.3f}")
                
                with chart_cols[i % 2]:
                    st.subheader(f"Top 5 Worst: {display_name}")
                    # Use st.dataframe for a table look, matching the size
                    st.dataframe(df_table, use_container_width=True, hide_index=True)


        st.markdown("---")

        st.subheader("Schools Detail with Deficiency Ratios")
        
        # Prepare a readable DataFrame for display
        ratios_display = ratios_df.rename(columns=ratio_mapping)
        cols_to_show = ['school_name', 'enrolled_students'] + list(ratio_mapping.values())
        

        st.dataframe(ratios_display[cols_to_show], use_container_width=True, height=500)
