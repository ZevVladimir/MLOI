import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.ticker import LogLocator, NullFormatter
from utils.data_and_loading_functions import split_orb_inf, timed

# used to find the location of a number within bins 
def get_bin_loc(bin_edges,search_num):
    # Find the location where 0 would be placed. Accounts for if there is no 0 by finding between which bins but also will find 0 if it is there
    upper_index = np.searchsorted(bin_edges, search_num, side='right')
    lower_index = upper_index - 1

    lower_edge = bin_edges[lower_index]
    upper_edge = bin_edges[upper_index]

    # Interpolate the fractional position of 0 between the two edges
    fraction = (search_num - lower_edge) / (upper_edge - lower_edge)
    search_loc = lower_index + fraction
    
    return search_loc

def gen_ticks(bin_edges,spacing=6):
    ticks = []
    tick_loc = []

    # Add every spacing bin edge
    ticks.extend(bin_edges[::spacing])

    # Ensure the first and last bin edges are included
    ticks.extend([bin_edges[0], bin_edges[-1]])

    tick_loc = np.arange(bin_edges.size)[::spacing].tolist()
    tick_loc.extend([0,bin_edges.size-1])

    zero_loc = get_bin_loc(bin_edges,0)

    # only add the tick if it is noticeably far away from 0
    if zero_loc > 0.05:
        tick_loc.append(zero_loc)
        ticks.append(0)

    # Remove ticks that will get rounded down to 0
    ticks = np.round(ticks,2).tolist()
    rmv_ticks = np.where(ticks == 0)[0]
    if rmv_ticks.size > 0:
        ticks = ticks.pop(rmv_ticks)
        tick_loc = tick_loc.pop(rmv_ticks)

    # Remove duplicates and sort the list
    ticks = sorted(set(ticks))
    tick_loc = sorted(set(tick_loc))
    
    return tick_loc, ticks

def imshow_plot(ax, img, extent, x_label="", y_label="", text="", title="", hide_xticks=False, hide_yticks=False, xticks = None, yticks = None, linthrsh = 0, axisfontsize=20, return_img=False, kwargs={}):
    ret_img=ax.imshow(img["hist"].T, interpolation="none", **kwargs)
    
    xticks_loc, xticks = gen_ticks(img["x_edge"])
    yticks_loc, yticks = gen_ticks(img["y_edge"])
    
    if not hide_xticks:
        ax.set_xticks(xticks_loc,xticks)
    if not hide_yticks:
        ax.set_yticks(yticks_loc,yticks)
        
    linthrsh_loc = get_bin_loc(img["y_edge"],linthrsh)
    ax.axhline(y=linthrsh_loc, color='grey', linestyle='--', alpha=1)
    if np.where(np.array(yticks,dtype=np.float32) < 0)[0].size > 0:
        neg_linthrsh_loc = get_bin_loc(img["y_edge"],-linthrsh)
        ax.axhline(y=neg_linthrsh_loc, color='grey', linestyle='--', alpha=1)

    if text != "":
        ax.text(.01,.03, text, ha="left", va="bottom", transform=ax.transAxes, fontsize=18, bbox={"facecolor":'white',"alpha":0.9,})
        
    if title != "":
        ax.set_title(title,fontsize=24)
    if x_label != "":
        ax.set_xlabel(x_label,fontsize=axisfontsize)
    if y_label != "":
        ax.set_ylabel(y_label,fontsize=axisfontsize)
    if hide_xticks:
        ax.tick_params(axis='x', which='both',bottom=False,labelbottom=False)
    else:
        ax.tick_params(axis='x', which='major', labelsize=16)
        ax.tick_params(axis='x', which='minor', labelsize=14)
         
    if hide_yticks:
        ax.tick_params(axis='y', which='both',left=False,labelleft=False)
    else:
        ax.tick_params(axis='y', which='major', labelsize=16)
        ax.tick_params(axis='y', which='minor', labelsize=14)
           
    if return_img:
        return ret_img

# Uses np.histogram2d to create a histogram and the edges of the histogram in one dictionary
# Can also do a linear binning then a logarithmic binning (similar to symlog) but allows for 
# special case of only positive log and not negative log
def histogram(x,y,use_bins,hist_range,min_ptl,set_ptl,split_yscale_dict=None):
    #TODO add so that it is doable for x axis too
    if split_yscale_dict != None:
        linthrsh = split_yscale_dict["linthrsh"]
        lin_nbin = split_yscale_dict["lin_nbin"]
        log_nbin = split_yscale_dict["log_nbin"]
        
        y_range = hist_range[1]
        # if the y axis goes to the negatives
        if y_range[0] < 0:
            lin_bins = np.linspace(-linthrsh,linthrsh,lin_nbin,endpoint=False)
            neg_log_bins = -np.logspace(np.log10(-y_range[0]),np.log10(linthrsh),log_nbin,endpoint=False)
            pos_log_bins = np.logspace(np.log10(linthrsh),np.log10(y_range[1]),log_nbin)
            y_bins = np.concatenate([neg_log_bins,lin_bins,pos_log_bins])
            
        else:
            lin_bins = np.linspace(y_range[0],linthrsh,lin_nbin,endpoint=False)
            pos_log_bins = np.logspace(np.log10(linthrsh),np.log10(y_range[1]),log_nbin)
            y_bins = np.concatenate([lin_bins,pos_log_bins])

        use_bins[1] = y_bins

    hist = np.histogram2d(x, y, bins=use_bins, range=hist_range)
    
    fin_hist = {
        "hist":hist[0],
        "x_edge":hist[1],
        "y_edge":hist[2]
    }
    
    fin_hist["hist"][fin_hist["hist"] < min_ptl] = set_ptl
    
    return fin_hist

def scale_hists(inc_hist, act_hist, act_min, inc_min):
    scaled_hist = {
        "x_edge":act_hist["x_edge"],
        "y_edge":act_hist["y_edge"]
    }
    scaled_hist["hist"] = np.divide(inc_hist["hist"],act_hist["hist"],out=np.zeros_like(inc_hist["hist"]), where=act_hist["hist"]!=0)
    
    scaled_hist["hist"] = np.where((inc_hist["hist"] < 1) & (act_hist["hist"] >= act_min), inc_min, scaled_hist["hist"])
    # Where there are miss classified particles but they won't show up on the image, set them to the min
    scaled_hist["hist"] = np.where((inc_hist["hist"] >= 1) & (scaled_hist["hist"] < inc_min) & (act_hist["hist"] >= act_min), inc_min, scaled_hist["hist"])
    
    return scaled_hist

# scale the number of particles so that there are no lines. Plot N / N_tot / dx / dy
def normalize_hists(hist,tot_nptl,min_ptl):
    scaled_hist = {
        "x_edge":hist["x_edge"],
        "y_edge":hist["y_edge"]
    }
    
    dx = np.diff(hist["x_edge"])
    dy = np.diff(hist["y_edge"])
    
    scaled_hist["hist"] = hist["hist"] / tot_nptl / dx[:,None] / dy[None,:]
    # scale all bins where lower than the min to the min
    scaled_hist["hist"] = np.where((scaled_hist["hist"] < min_ptl) & (scaled_hist["hist"] > 0), min_ptl, scaled_hist["hist"])
    
    return scaled_hist

def plot_full_ptl_dist(p_corr_labels, p_r, p_rv, p_tv, c_r, c_rv, split_yscale_dict, num_bins, save_loc):
    with timed("Finished Full Ptl Dist Plot"):
        print("Starting Full Ptl Dist Plot")
        
        linthrsh = split_yscale_dict["linthrsh"]
        log_nbin = split_yscale_dict["log_nbin"]
        
        p_r_range = [np.min(p_r),np.max(p_r)]
        p_rv_range = [np.min(p_rv),np.max(p_rv)]
        p_tv_range = [np.min(p_tv),np.max(p_tv)]
        
        act_min_ptl = 10
        set_ptl = 0
        scale_min_ptl = 1e-4
        
        inf_p_r, orb_p_r = split_orb_inf(p_r,p_corr_labels)
        inf_p_rv, orb_p_rv = split_orb_inf(p_rv,p_corr_labels)
        inf_p_tv, orb_p_tv = split_orb_inf(p_tv,p_corr_labels)
        inf_c_r, orb_c_r = split_orb_inf(c_r,p_corr_labels)
        inf_c_rv, orb_c_rv = split_orb_inf(c_rv,p_corr_labels)
        
        # Use the binning from all particles for the orbiting and infalling plots and the secondary snap to keep it consistent
        all_p_r_p_rv = histogram(p_r,p_rv,use_bins=[num_bins,num_bins],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        all_p_r_p_tv = histogram(p_r,p_tv,use_bins=[num_bins,num_bins],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        all_p_rv_p_tv = histogram(p_rv,p_tv,use_bins=[num_bins,num_bins],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        all_c_r_c_rv = histogram(c_r,c_rv,use_bins=[all_p_r_p_rv["x_edge"],all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        
        inf_p_r_p_rv = histogram(inf_p_r,inf_p_rv,use_bins=[all_p_r_p_rv["x_edge"],all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        inf_p_r_p_tv = histogram(inf_p_r,inf_p_tv,use_bins=[all_p_r_p_tv["x_edge"],all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        inf_p_rv_p_tv = histogram(inf_p_rv,inf_p_tv,use_bins=[all_p_rv_p_tv["x_edge"],all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        inf_c_r_c_rv = histogram(inf_c_r,inf_c_rv,use_bins=[all_c_r_c_rv["x_edge"],all_c_r_c_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        
        orb_p_r_p_rv = histogram(orb_p_r,orb_p_rv,use_bins=[all_p_r_p_rv["x_edge"],all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        orb_p_r_p_tv = histogram(orb_p_r,orb_p_tv,use_bins=[all_p_r_p_tv["x_edge"],all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        orb_p_rv_p_tv = histogram(orb_p_rv,orb_p_tv,use_bins=[all_p_rv_p_tv["x_edge"],all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        orb_c_r_c_rv = histogram(orb_c_r,orb_c_rv,use_bins=[all_p_r_p_rv["x_edge"],all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=set_ptl,split_yscale_dict=split_yscale_dict)
        
        tot_nptl = p_r.shape[0]
        
        # normalize the number of particles so that there are no lines.
        all_p_r_p_rv = normalize_hists(all_p_r_p_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        all_p_r_p_tv = normalize_hists(all_p_r_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        all_p_rv_p_tv = normalize_hists(all_p_rv_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        all_c_r_c_rv = normalize_hists(all_c_r_c_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)

        inf_p_r_p_rv = normalize_hists(inf_p_r_p_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        inf_p_r_p_tv = normalize_hists(inf_p_r_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        inf_p_rv_p_tv = normalize_hists(inf_p_rv_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        inf_c_r_c_rv = normalize_hists(inf_c_r_c_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)

        orb_p_r_p_rv = normalize_hists(orb_p_r_p_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        orb_p_r_p_tv = normalize_hists(orb_p_r_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        orb_p_rv_p_tv = normalize_hists(orb_p_rv_p_tv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        orb_c_r_c_rv = normalize_hists(orb_c_r_c_rv,tot_nptl=tot_nptl,min_ptl=scale_min_ptl)
        
        # Can just do the all particle arrays since inf/orb will have equal or less
        max_ptl = np.max(np.array([np.max(all_p_r_p_rv["hist"]),np.max(all_p_r_p_tv["hist"]),np.max(all_p_rv_p_tv["hist"]),np.max(all_c_r_c_rv["hist"])]))
        
        cividis_cmap = plt.get_cmap("cividis_r")
        cividis_cmap.set_under(color='white')  
        
        plot_kwargs = {
                "vmin":scale_min_ptl,
                "vmax":max_ptl,
                "norm":"log",
                "origin":"lower",
                "aspect":"auto",
                "cmap":cividis_cmap,
        }
        
        rv_yticks=[-linthrsh,np.round(-linthrsh/2,2),0,np.round(linthrsh/2,2),linthrsh]
        rv_yticks.extend(np.logspace(np.log10(linthrsh),np.log10(p_rv_range[1]),int(np.floor(log_nbin/5))+1))
        rv_yticks.extend(-np.logspace(np.log10(-p_rv_range[0]),np.log10(linthrsh),int(np.floor(log_nbin/5))+1))
        
        tv_yticks = [0,np.round(linthrsh/2,2),linthrsh]
        tv_yticks.extend(np.logspace(np.log10(linthrsh),np.log10(p_tv_range[1]),int(np.floor(log_nbin/5))+1))
        
        
        widths = [4,4,4,4,.5]
        heights = [0.15,4,4,4] # have extra row up top so there is space for the title
        
        fig = plt.figure(constrained_layout=True, figsize=(30,25))
        gs = fig.add_gridspec(len(heights),len(widths),width_ratios = widths, height_ratios = heights, hspace=0, wspace=0)
        
        imshow_plot(fig.add_subplot(gs[1,0]),all_p_r_p_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",text="All Particles",title="Primary Snap",hide_xticks=True,yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[1,1]),all_p_r_p_tv,extent=p_r_range+p_tv_range,y_label="$v_t/v_{200m}$",hide_xticks=True,yticks=tv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[1,2]),all_p_rv_p_tv,extent=p_rv_range+p_tv_range,hide_xticks=True,hide_yticks=True,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[1,3]),all_c_r_c_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",title="Secondary Snap",hide_xticks=True,yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        
        imshow_plot(fig.add_subplot(gs[2,0]),inf_p_r_p_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",text="Infalling Particles",hide_xticks=True,yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[2,1]),inf_p_r_p_tv,extent=p_r_range+p_tv_range,y_label="$v_t/v_{200m}$",hide_xticks=True,yticks=tv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[2,2]),inf_p_rv_p_tv,extent=p_rv_range+p_tv_range,hide_xticks=True,hide_yticks=True,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[2,3]),inf_c_r_c_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",hide_xticks=True,yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
                    
        imshow_plot(fig.add_subplot(gs[3,0]),orb_p_r_p_rv,extent=p_r_range+p_rv_range,x_label="$r/R_{200m}$",y_label="$v_r/v_{200m}$",text="Orbiting Particles",yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[3,1]),orb_p_r_p_tv,extent=p_r_range+p_tv_range,x_label="$r/R_{200m}$",y_label="$v_t/v_{200m}$",yticks=tv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[3,2]),orb_p_rv_p_tv,extent=p_rv_range+p_tv_range,x_label="$v_r/v_{200m}$",hide_yticks=True,linthrsh=linthrsh,kwargs=plot_kwargs)
        imshow_plot(fig.add_subplot(gs[3,3]),orb_c_r_c_rv,extent=p_r_range+p_rv_range,x_label="$r/R_{200m}$",y_label="$v_r/v_{200m}$",yticks=rv_yticks,linthrsh=linthrsh,kwargs=plot_kwargs)

        color_bar = plt.colorbar(mpl.cm.ScalarMappable(norm=mpl.colors.LogNorm(vmin=scale_min_ptl, vmax=max_ptl),cmap=cividis_cmap), cax=plt.subplot(gs[1:,-1]))
        color_bar.set_label("N / N_tot / dx / dy",fontsize=16)
        color_bar.ax.tick_params(labelsize=14)
        
        fig.savefig(save_loc + "ptl_distr.png")

def plot_miss_class_dist(p_corr_labels, p_ml_labels, p_r, p_rv, p_tv, c_r, c_rv, split_yscale_dict, num_bins, save_loc, model_info,dataset_name):
    with timed("Finished Miss Class Dist Plot"):
        print("Starting Miss Class Dist Plot")

        linthrsh = split_yscale_dict["linthrsh"]
        log_nbin = split_yscale_dict["log_nbin"]

        p_r_range = [np.min(p_r),np.max(p_r)]
        p_rv_range = [np.min(p_rv),np.max(p_rv)]
        p_tv_range = [np.min(p_tv),np.max(p_tv)]
        
        inc_min_ptl = 1e-4
        act_min_ptl = 10
        act_set_ptl = 0

        # inc_inf: particles that are actually infalling but labeled as orbiting
        # inc_orb: particles that are actually orbiting but labeled as infalling
        inc_inf = np.where((p_ml_labels == 1) & (p_corr_labels == 0))[0]
        inc_orb = np.where((p_ml_labels == 0) & (p_corr_labels == 1))[0]
        num_inf = np.where(p_corr_labels == 0)[0].shape[0]
        num_orb = np.where(p_corr_labels == 1)[0].shape[0]
        tot_num_inc = inc_orb.shape[0] + inc_inf.shape[0]
        tot_num_ptl = num_orb + num_inf

        missclass_dict = {
            "Total Num of Particles": tot_num_ptl,
            "Num Incorrect Infalling Particles": str(inc_inf.shape[0])+", "+str(np.round(((inc_inf.shape[0]/num_inf)*100),2))+"% of infalling ptls",
            "Num Incorrect Orbiting Particles": str(inc_orb.shape[0])+", "+str(np.round(((inc_orb.shape[0]/num_orb)*100),2))+"% of orbiting ptls",
            "Num Incorrect All Particles": str(tot_num_inc)+", "+str(np.round(((tot_num_inc/tot_num_ptl)*100),2))+"% of all ptls",
        }
        
        if "Results" not in model_info:
            model_info["Results"] = {}
        
        if dataset_name not in model_info["Results"]:
            model_info["Results"][dataset_name]={}
        model_info["Results"][dataset_name]["Primary Snap"] = missclass_dict
        
        inc_inf_p_r = p_r[inc_inf]
        inc_orb_p_r = p_r[inc_orb]
        inc_inf_p_rv = p_rv[inc_inf]
        inc_orb_p_rv = p_rv[inc_orb]
        inc_inf_p_tv = p_tv[inc_inf]
        inc_orb_p_tv = p_tv[inc_orb]
        inc_inf_c_r = c_r[inc_inf]
        inc_orb_c_r = c_r[inc_orb]
        inc_inf_c_rv = c_rv[inc_inf]
        inc_orb_c_rv = c_rv[inc_orb]

        act_inf_p_r, act_orb_p_r = split_orb_inf(p_r, p_corr_labels)
        act_inf_p_rv, act_orb_p_rv = split_orb_inf(p_rv, p_corr_labels)
        act_inf_p_tv, act_orb_p_tv = split_orb_inf(p_tv, p_corr_labels)
        act_inf_c_r, act_orb_c_r = split_orb_inf(c_r, p_corr_labels)
        act_inf_c_rv, act_orb_c_rv = split_orb_inf(c_rv, p_corr_labels)
        
        # Create histograms for all particles and then for the incorrect particles
        # Use the binning from all particles for the orbiting and infalling plots and the secondary snap to keep it consistent
        act_all_p_r_p_rv = histogram(p_r,p_rv,use_bins=[num_bins,num_bins],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_all_p_r_p_tv = histogram(p_r,p_tv,use_bins=[num_bins,num_bins],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_all_p_rv_p_tv = histogram(p_rv,p_tv,use_bins=[num_bins,num_bins],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_all_c_r_c_rv = histogram(c_r,c_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        
        act_inf_p_r_p_rv = histogram(act_inf_p_r,act_inf_p_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_inf_p_r_p_tv = histogram(act_inf_p_r,act_inf_p_tv,use_bins=[act_all_p_r_p_tv["x_edge"],act_all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_inf_p_rv_p_tv = histogram(act_inf_p_rv,act_inf_p_tv,use_bins=[act_all_p_rv_p_tv["x_edge"],act_all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_inf_c_r_c_rv = histogram(act_inf_c_r,act_inf_c_rv,use_bins=[act_all_c_r_c_rv["x_edge"],act_all_c_r_c_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        
        act_orb_p_r_p_rv = histogram(act_orb_p_r,act_orb_p_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_orb_p_r_p_tv = histogram(act_orb_p_r,act_orb_p_tv,use_bins=[act_all_p_r_p_tv["x_edge"],act_all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_orb_p_rv_p_tv = histogram(act_orb_p_rv,act_orb_p_tv,use_bins=[act_all_p_rv_p_tv["x_edge"],act_all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        act_orb_c_r_c_rv = histogram(act_orb_c_r,act_orb_c_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
            
        inc_inf_p_r_p_rv = histogram(inc_inf_p_r,inc_inf_p_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_inf_p_r_p_tv = histogram(inc_inf_p_r,inc_inf_p_tv,use_bins=[act_all_p_r_p_tv["x_edge"],act_all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_inf_p_rv_p_tv = histogram(inc_inf_p_rv,inc_inf_p_tv,use_bins=[act_all_p_rv_p_tv["x_edge"],act_all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_inf_c_r_c_rv = histogram(inc_inf_c_r,inc_inf_c_rv,use_bins=[act_all_c_r_c_rv["x_edge"],act_all_c_r_c_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        
        inc_orb_p_r_p_rv = histogram(inc_orb_p_r,inc_orb_p_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_orb_p_r_p_tv = histogram(inc_orb_p_r,inc_orb_p_tv,use_bins=[act_all_p_r_p_tv["x_edge"],act_all_p_r_p_tv["y_edge"]],hist_range=[p_r_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_orb_p_rv_p_tv = histogram(inc_orb_p_rv,inc_orb_p_tv,use_bins=[act_all_p_rv_p_tv["x_edge"],act_all_p_rv_p_tv["y_edge"]],hist_range=[p_rv_range,p_tv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)
        inc_orb_c_r_c_rv = histogram(inc_orb_c_r,inc_orb_c_rv,use_bins=[act_all_p_r_p_rv["x_edge"],act_all_p_r_p_rv["y_edge"]],hist_range=[p_r_range,p_rv_range],min_ptl=act_min_ptl,set_ptl=act_set_ptl,split_yscale_dict=split_yscale_dict)

        
        inc_all_p_r_p_rv = {
            "hist":inc_inf_p_r_p_rv["hist"] + inc_orb_p_r_p_rv["hist"],
            "x_edge":act_all_p_r_p_rv["x_edge"],
            "y_edge":act_all_p_r_p_rv["y_edge"]
        }
        inc_all_p_r_p_tv = {
            "hist":inc_inf_p_r_p_tv["hist"] + inc_orb_p_r_p_tv["hist"],
            "x_edge":act_all_p_r_p_tv["x_edge"],
            "y_edge":act_all_p_r_p_tv["y_edge"]
        }
        inc_all_p_rv_p_tv = {
            "hist":inc_inf_p_rv_p_tv["hist"] + inc_orb_p_rv_p_tv["hist"],
            "x_edge":act_all_p_rv_p_tv["x_edge"],
            "y_edge":act_all_p_rv_p_tv["y_edge"]
        }
        inc_all_c_r_c_rv = {
            "hist":inc_inf_c_r_c_rv["hist"] + inc_orb_c_r_c_rv["hist"],
            "x_edge":act_all_c_r_c_rv["x_edge"],
            "y_edge":act_all_c_r_c_rv["y_edge"]
        }
        
        
        scale_inc_all_p_r_p_rv = scale_hists(inc_all_p_r_p_rv,act_all_p_r_p_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_all_p_r_p_tv = scale_hists(inc_all_p_r_p_tv,act_all_p_r_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_all_p_rv_p_tv = scale_hists(inc_all_p_rv_p_tv,act_all_p_rv_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_all_c_r_c_rv = scale_hists(inc_all_c_r_c_rv,act_all_c_r_c_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        
        scale_inc_inf_p_r_p_rv = scale_hists(inc_inf_p_r_p_rv,act_inf_p_r_p_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_inf_p_r_p_tv = scale_hists(inc_inf_p_r_p_tv,act_inf_p_r_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_inf_p_rv_p_tv = scale_hists(inc_inf_p_rv_p_tv,act_inf_p_rv_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_inf_c_r_c_rv = scale_hists(inc_inf_c_r_c_rv,act_inf_c_r_c_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        
        scale_inc_orb_p_r_p_rv = scale_hists(inc_orb_p_r_p_rv,act_orb_p_r_p_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_orb_p_r_p_tv = scale_hists(inc_orb_p_r_p_tv,act_orb_p_r_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_orb_p_rv_p_tv = scale_hists(inc_orb_p_rv_p_tv,act_orb_p_rv_p_tv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        scale_inc_orb_c_r_c_rv = scale_hists(inc_orb_c_r_c_rv,act_orb_c_r_c_rv,act_min=act_min_ptl,inc_min=inc_min_ptl)
        
        magma_cmap = plt.get_cmap("magma_r")
        magma_cmap.set_under(color='white')
        
        scale_miss_class_args = {
                "vmin":inc_min_ptl,
                "vmax":1,
                "norm":"log",
                "origin":"lower",
                "aspect":"auto",
                "cmap":magma_cmap,
        }
        
        rv_yticks=[-linthrsh,np.round(-linthrsh/2,2),0,np.round(linthrsh/2,2),linthrsh]
        rv_yticks.extend(np.logspace(np.log10(linthrsh),np.log10(p_rv_range[1]),int(np.floor(log_nbin/5))+1))
        rv_yticks.extend(-np.logspace(np.log10(-p_rv_range[0]),np.log10(linthrsh),int(np.floor(log_nbin/5))+1))
        
        tv_yticks = [0,np.round(linthrsh/2,2),linthrsh]
        tv_yticks.extend(np.logspace(np.log10(linthrsh),np.log10(p_tv_range[1]),int(np.floor(log_nbin/5))+1))
        
        widths = [4,4,4,4,.5]
        heights = [0.12,4,4,4]
        
        fig = plt.figure(constrained_layout=True,figsize=(30,25))
        gs = fig.add_gridspec(len(heights),len(widths),width_ratios = widths, height_ratios = heights, hspace=0, wspace=0)

        imshow_plot(fig.add_subplot(gs[1,0]), scale_inc_all_p_r_p_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",hide_xticks=True,text="All Misclassified\nScaled",yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[1,1]), scale_inc_all_p_r_p_tv,extent=p_r_range+p_tv_range,y_label="$v_t/v_{200m}$",hide_xticks=True,yticks=tv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[1,2]), scale_inc_all_p_rv_p_tv,extent=p_rv_range+p_tv_range,hide_xticks=True,hide_yticks=True,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[1,3]), scale_inc_all_c_r_c_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",hide_xticks=True,text="All Misclassified\nScaled",yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)

        imshow_plot(fig.add_subplot(gs[2,0]), scale_inc_inf_p_r_p_rv,extent=p_r_range+p_rv_range,hide_xticks=True,y_label="$v_r/v_{200m}$",text="Label: Orbit\nReal: Infall",yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args, title="Primary Snap")
        imshow_plot(fig.add_subplot(gs[2,1]), scale_inc_inf_p_r_p_tv,extent=p_r_range+p_tv_range,y_label="$v_t/v_{200m}$",hide_xticks=True,yticks=tv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[2,2]), scale_inc_inf_p_rv_p_tv,extent=p_rv_range+p_tv_range,hide_xticks=True,hide_yticks=True,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[2,3]), scale_inc_inf_c_r_c_rv,extent=p_r_range+p_rv_range,y_label="$v_r/v_{200m}$",text="Label: Orbit\nReal: Infall",hide_xticks=True,yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args, title="Secondary Snap")
        
        imshow_plot(fig.add_subplot(gs[3,0]), scale_inc_orb_p_r_p_rv,extent=p_r_range+p_rv_range,x_label="$r/R_{200m}$",y_label="$v_r/v_{200m}$",text="Label: Infall\nReal: Orbit",yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[3,1]), scale_inc_orb_p_r_p_tv,extent=p_r_range+p_tv_range,x_label="$r/R_{200m}$",y_label="$v_t/v_{200m}$",yticks=tv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[3,2]), scale_inc_orb_p_rv_p_tv,extent=p_rv_range+p_tv_range,x_label="$v_r/v_{200m}$",hide_yticks=True,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        imshow_plot(fig.add_subplot(gs[3,3]), scale_inc_orb_c_r_c_rv,extent=p_r_range+p_rv_range,x_label="$r/R_{200m}$",y_label="$v_r/v_{200m}$",text="Label: Infall\nReal: Orbit",yticks=rv_yticks,linthrsh=linthrsh,kwargs=scale_miss_class_args)
        
        color_bar = plt.colorbar(mpl.cm.ScalarMappable(norm=mpl.colors.LogNorm(vmin=inc_min_ptl, vmax=1),cmap=magma_cmap), cax=plt.subplot(gs[1:,-1]))
        color_bar.set_label("Num Incorrect Particles (inf/orb) / Total Particles (inf/orb)",fontsize=16)
        color_bar.ax.tick_params(labelsize=14)
        
        fig.savefig(save_loc + "scaled_miss_class.png")

def plot_perr_err():
    return
