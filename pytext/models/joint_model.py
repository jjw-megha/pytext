#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Union

from pytext.config import ConfigBase
from pytext.config.contextual_intent_slot import ModelInput
from pytext.data import CommonMetadata
from pytext.models.model import Model
from pytext.models.module import create_module

from .decoders import IntentSlotModelDecoder
from .output_layers.intent_slot_output_layer import IntentSlotOutputLayer
from .output_layers.word_tagging_output_layer import CRFOutputLayer
from .representations.bilstm_doc_slot_attention import BiLSTMDocSlotAttention
from .representations.jointcnn_rep import JointCNNRepresentation


class JointModel(Model):
    """
    A joint intent-slot model. This is framed as a model to do document
    classification model and word tagging tasks where the embedding and text
    representation layers are shared for both tasks.

    The supported representation layers are based on bidirectional LSTM or CNN.

    It can be instantiated just like any other :class:`~Model`.
    """

    class Config(ConfigBase):
        representation: Union[
            BiLSTMDocSlotAttention.Config, JointCNNRepresentation.Config
        ] = BiLSTMDocSlotAttention.Config()
        output_layer: IntentSlotOutputLayer.Config = (IntentSlotOutputLayer.Config())
        decoder: IntentSlotModelDecoder.Config = IntentSlotModelDecoder.Config()
        default_doc_loss_weight: float = 0.2
        default_word_loss_weight: float = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # CRF module has parameters and it's forward function is not called in
        # model's forward function because of ONNX compatibility issue. This will
        # not work with DDP, thus setting find_unused_parameters to False to work
        # around, can be removed once DDP support params not used in model forward
        # function
        if isinstance(self.output_layer.word_output, CRFOutputLayer):
            self.find_unused_parameters = False

    @classmethod
    def from_config(cls, model_config, feat_config, metadata: CommonMetadata):
        embedding = cls.create_embedding(feat_config, metadata)
        representation = create_module(
            model_config.representation, embed_dim=embedding.embedding_dim
        )
        dense_feat_dim = 0
        for decoder_feat in (ModelInput.DENSE,):  # Only 1 right now.
            if getattr(feat_config, decoder_feat, False):
                dense_feat_dim = getattr(feat_config, ModelInput.DENSE).dim

        doc_label_meta, word_label_meta = metadata.target
        decoder = create_module(
            model_config.decoder,
            in_dim_doc=representation.doc_representation_dim + dense_feat_dim,
            in_dim_word=representation.word_representation_dim + dense_feat_dim,
            out_dim_doc=doc_label_meta.vocab_size,
            out_dim_word=word_label_meta.vocab_size,
        )

        if dense_feat_dim > 0:
            decoder.num_decoder_modules = 1
        output_layer = create_module(
            model_config.output_layer, doc_label_meta, word_label_meta
        )
        return cls(embedding, representation, decoder, output_layer)
