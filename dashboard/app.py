import streamlit as st
import pandas as pd
from google.cloud import bigquery
import os

# Set page config
st.set_page_config(page_title="Document Processing Dashboard", page_icon="📄", layout="wide")

st.title("📄 Processed Documents Dashboard")
st.markdown("View and filter metadata extracted by the serverless document processing pipeline.")

# Configuration
# Default to common values if env vars are not set
project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
dataset_name = os.environ.get("BQ_DATASET", "document_processing")
table_name = os.environ.get("BQ_TABLE", "metadata")

@st.cache_data(ttl=60) # Cache data for 60 seconds
def fetch_data():
    """Fetches data from BigQuery."""
    try:
        client = bigquery.Client(project=project_id)
        # Use client's project if explicit project_id is not set
        proj = project_id if project_id else client.project
        
        query = f"""
            SELECT filename, upload_time, tags, word_count, processed_time
            FROM `{proj}.{dataset_name}.{table_name}`
            ORDER BY upload_time DESC
        """
        
        # Load into pandas dataframe
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        st.error(f"Error fetching data from BigQuery: {e}")
        return pd.DataFrame()

# Fetch data
with st.spinner("Loading data from BigQuery..."):
    df = fetch_data()

if df.empty:
    st.warning("No data found or unable to connect to BigQuery. Ensure you have uploaded files and are authenticated.")
else:
    # Process tags column (it's a comma-separated string from our processor)
    # E.g., "invoice, report, scan" -> ["invoice", "report", "scan"]
    def split_tags(tag_str):
        if pd.isna(tag_str) or not isinstance(tag_str, str):
            return []
        return [t.strip() for t in tag_str.split(",") if t.strip()]
        
    df['parsed_tags'] = df['tags'].apply(split_tags)
    
    # Extract unique tags for the filter
    all_tags = set()
    for tags_list in df['parsed_tags']:
        all_tags.update(tags_list)
    
    # Filter UI
    st.subheader("Filter Documents")
    col1, col2 = st.columns(2)
    
    with col1:
        selected_tags = st.multiselect("Filter by Tags", options=sorted(list(all_tags)))
    
    with col2:
        search_filename = st.text_input("Search Filename")
        
    # Apply filters
    filtered_df = df.copy()
    
    if selected_tags:
        # Keep rows where AT LEAST ONE selected tag is in the parsed_tags list
        filtered_df = filtered_df[filtered_df['parsed_tags'].apply(
            lambda x: any(tag in x for tag in selected_tags)
        )]
        
    if search_filename:
        filtered_df = filtered_df[filtered_df['filename'].str.contains(search_filename, case=False, na=False)]
        
    # Display metrics
    st.markdown("---")
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Documents", len(filtered_df))
    col_m2.metric("Total Words Processed", int(filtered_df['word_count'].sum()) if not filtered_df.empty else 0)
    col_m3.metric("Unique Tags", len(all_tags))
    
    # Display table (drop the parsed_tags helper column for cleaner display)
    st.markdown("### Results")
    display_df = filtered_df.drop(columns=['parsed_tags'])
    
    # Format datetime columns for nicer display
    if 'upload_time' in display_df.columns:
        display_df['upload_time'] = pd.to_datetime(display_df['upload_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
    if 'processed_time' in display_df.columns:
        display_df['processed_time'] = pd.to_datetime(display_df['processed_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
    st.dataframe(display_df, use_container_width=True)
