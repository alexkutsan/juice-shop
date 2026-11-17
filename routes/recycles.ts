/*
 * Copyright (c) 2014-2025 Bjoern Kimminich & the OWASP Juice Shop contributors.
 * SPDX-License-Identifier: MIT
 */

import { type NextFunction, type Request, type Response } from 'express'
import { RecycleModel } from '../models/recycle'
import { AddressModel } from '../models/address'

import * as utils from '../lib/utils'

export const getRecycleItem = () => (req: Request, res: Response) => {
  RecycleModel.findAll({
    where: {
      id: JSON.parse(req.params.id)
    }
  }).then((Recycle) => {
    return res.send(utils.queryResultToJson(Recycle))
  }).catch((_: unknown) => {
    return res.send('Error fetching recycled items. Please try again')
  })
}

export const blockRecycleItems = () => (req: Request, res: Response) => {
  const errMsg = { err: 'Sorry, this endpoint is not supported.' }
  return res.send(utils.queryResultToJson(errMsg))
}

export const authorizeRecycleAddress = () => async (req: Request, res: Response, next: NextFunction) => {
  const suppliedAddressId = req.body.AddressId
  const addressId = typeof suppliedAddressId === 'number'
    ? suppliedAddressId
    : (typeof suppliedAddressId === 'string' && /^\d+$/.test(suppliedAddressId) ? Number(suppliedAddressId) : NaN)

  if (!Number.isSafeInteger(addressId) || addressId <= 0) {
    return res.status(404).json({ status: 'error', message: 'Not Found' })
  }

  try {
    const address = await AddressModel.findOne({
      attributes: ['id'],
      where: { id: addressId, UserId: req.body.UserId }
    })
    if (address == null) {
      return res.status(404).json({ status: 'error', message: 'Not Found' })
    }
    req.body.AddressId = addressId
    next()
  } catch (error) {
    next(error)
  }
}
