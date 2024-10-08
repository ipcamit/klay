from typing import Tuple

import torch
from torch_scatter import scatter

from torch import nn
from torch_geometric import nn  as gnn
from torch_geometric.loader import DataLoader



class EGCL(gnn.MessagePassing):
    """
    \mathbf{m}_{ij} = \phi_e(\mathbf{h}_i^l, \mathbf{h}_j^i,\|r_i - r_j \|^2, a_{ij})
    r_i^{l+1} = r_i^l + C\sum (r_i^l - r_j^l)\phi_r(\mathbf{m}_{ij})
    \mathbf{m}_i= \sum_{i\ne j}\mathbf{m}_{ij}
    \mathbf{h}_i^{l+1} = \phi_h(\mathbf{h}_i^l,\mathbf{m}_i)
    """
    propagate_type = { 
        "h": torch.Tensor,
        "coords" : torch.Tensor,
        "shift_vectors" : torch.Tensor,
        "batch": torch.Tensor,
        "i_batch": torch.Tensor
        }

    def __init__(self, in_node_fl, hidden_node_fl, edge_fl=0, act_fn=nn.SiLU(), n_hidden_layers=1, normalize_radial=False):
        super().__init__(aggr="add")
        self.in_node_fl = int(in_node_fl)
        self.hidden_node_fl = int(hidden_node_fl)
        self.edge_fl = int(edge_fl)
        
        self.normalize_radial = normalize_radial
        self.C = torch.zeros(1)

        phi_h = []
        phi_e = []
        phi_r = []
        
        # input layers
        phi_e.append(nn.Linear(self.hidden_node_fl * 2 + 1 + edge_fl, self.hidden_node_fl))
        phi_e.append(act_fn)
        phi_r.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))
        phi_r.append(act_fn)
        phi_h.append(nn.Linear(self.hidden_node_fl + self.hidden_node_fl, self.hidden_node_fl))
        phi_h.append(act_fn)

        # hidden layers
        for i in range(n_hidden_layers):
            phi_e.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))
            phi_e.append(act_fn)
            phi_r.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))
            phi_r.append(act_fn)
            phi_h.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))
            phi_h.append(act_fn)

        # output layers
        phi_e.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))
        phi_r.append(nn.Linear(self.hidden_node_fl,1))
        phi_h.append(nn.Linear(self.hidden_node_fl, self.hidden_node_fl))

        self.phi_e = nn.Sequential(*phi_e)
        self.phi_r = nn.Sequential(*phi_r)
        self.phi_h = nn.Sequential(*phi_h)

    
    def forward(self, h:torch.Tensor, 
                      coords:torch.Tensor, 
                      edge_index:torch.Tensor, 
                      shift_vectors:torch.Tensor,
                      batch:torch.Tensor):
        n_atoms = scatter(torch.ones_like(batch),batch,dim=0,reduce="add")
        self.C = 1./(n_atoms - 1.)
        h, coords = self.propagate(edge_index, h = h, coords = coords, batch=batch, shift_vectors=shift_vectors, size=None) 
        return h, coords
        
    def message(self,h_i, h_j, coords_i, coords_j, shift_vectors)->Tuple[torch.Tensor,torch.Tensor]:

        dcoords = coords_j - coords_i - shift_vectors
        norm_dr = dcoords.pow(2).sum(1).sqrt()
        if self.normalize_radial:
            dcoords = dcoords/norm_dr
        # TODO: aij 

        mij = self.phi_e(torch.cat([h_i,h_j,torch.unsqueeze(norm_dr,1)],1))
        delrij = dcoords * self.phi_r(mij)
        return mij, delrij
        
    def aggregate(self,messages:Tuple[torch.Tensor,torch.Tensor],index, coords, batch)->Tuple[torch.Tensor,torch.Tensor]:
        m = scatter(messages[0],index,dim=0,reduce="add")
        dcoords = scatter(messages[1],index,dim=0,reduce="add")
        dcoords = dcoords * torch.unsqueeze(self.C[batch],1)
        coords_ = coords + dcoords
        return m, coords_
        
    def update(self, messages:Tuple[torch.Tensor,torch.Tensor],h:torch.Tensor)->Tuple[torch.Tensor,torch.Tensor]:
        h = self.phi_h(torch.cat([h,messages[0]],1))
        return h, messages[1]


# class EGNN(nn.Module):
#     def __init__(self, in_node_fl, hidden_node_fl, n_conv_l, act_fn=nn.SiLU()):
#         super(EGNN, self).__init__()
#         self.in_node_fl = in_node_fl        
#         self.hidden_node_fl = hidden_node_fl        
#         self.n_conv_l = n_conv_l

#         self.conv_module = nn.ModuleList(
#             [EGCL(hidden_node_fl,hidden_node_fl).jittable() for i in range(n_conv_l)]
#         )

#         self.mlp = nn.Sequential(
#             nn.Linear(hidden_node_fl, hidden_node_fl),
#             act_fn,
#             nn.Linear(hidden_node_fl,hidden_node_fl),
#             act_fn,
#             nn.Linear(hidden_node_fl,1)
#         )
        
#         self.embedding = nn.Sequential(
#             nn.Linear(self.in_node_fl, self.hidden_node_fl)
#         )
#         self.register_buffer("pow_vec", torch.arange(3))

#     def forward(self, x:torch.Tensor,
#                      coords:torch.Tensor,
#                      edge_index:torch.Tensor,
#                      shift_vectors:torch.Tensor,
#                      batch:torch.Tensor):
#         h0 = torch.unsqueeze(x/torch.max(x),1)
#         h0 = h0.pow(self.pow_vec)
#         h = self.embedding(h0)
#         for gcl in self.conv_module:
#             h, coords = gcl(h, r, edge_index, shift_vectors, batch)
#         E_local = self.mlp(h)
#         E = scatter(E_local, batch, dim=0, reduce="add")
#         return E

